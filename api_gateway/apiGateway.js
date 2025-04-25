const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const path = require('path');
const protoLoader = require('@grpc/proto-loader');
const grpc = require('@grpc/grpc-js');

const apiGateway = express();
apiGateway.use(express.json());

const USER_SERVICE_URL = process.env.USER_SERVICE_URL || 'http://user_service:5001';
const JWT_SECRET = process.env.JWT_SECRET || 'super-secret-key';
const POST_SERVICE_HOST = process.env.POST_SERVICE_HOST || 'content_service:50051';

const PROTO_PATH = path.join(__dirname, 'content.proto');
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true
});
const protoDescriptor = grpc.loadPackageDefinition(packageDefinition);
const postServicePackage = require('./postService'); // Проверьте путь!

const postClient = new postServicePackage.PostService(
  POST_SERVICE_HOST,
  grpc.credentials.createInsecure()
);
const { Kafka } = require('kafkajs');
const kafka = new Kafka({ brokers: ['kafka:9092'] });
const producer = kafka.producer();

(async () => {
  await producer.connect();
})();

function verifyToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  if (!authHeader) {
    return res.status(401).json({ error: 'Missing Authorization header' });
  }
  const token = authHeader.split(' ')[1];
  if (!token) {
    return res.status(401).json({ error: 'Invalid token format' });
  }
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.userId = decoded.sub;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

apiGateway.post('/users/register', async (req, res) => {
  try {
    const response = await axios.post(`${USER_SERVICE_URL}/users/register`, req.body, {
      headers: { 'Content-Type': 'application/json' }
    });
    return res.status(response.status).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(500).json({ error: err.message });
  }
});
apiGateway.get('/users/profile', verifyToken, async (req, res) => {
  try {
    const response = await axios.get(
      `${USER_SERVICE_URL}/users/profile`,
      {
        params: { user_id: req.userId },
        headers: { Authorization: req.headers.authorization }
      }
    );
    return res.status(response.status).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(500).json({ error: err.message });
  }
});

apiGateway.put('/users/profile', verifyToken, async (req, res) => {
  try {
    const response = await axios.put(
      `${USER_SERVICE_URL}/users/profile`,
      req.body,
      {
        params: { user_id: req.userId },
        headers: {
          Authorization: req.headers.authorization,
          'Content-Type': 'application/json'
        }
      }
    );
    return res.status(response.status).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(500).json({ error: err.message });
  }
});

apiGateway.post('/users/login', async (req, res) => {
  try {
    const response = await axios.post(`${USER_SERVICE_URL}/users/login`, req.body, {
      headers: { 'Content-Type': 'application/json' }
    });
    return res.status(response.status).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(500).json({ error: err.message });
  }
});

apiGateway.post('/posts', verifyToken, (req, res) => {
  const data = {
    title: req.body.title,
    description: req.body.description,
    creatorId: req.userId, // привязываем к пользователю из токена
    isPrivate: req.body.isPrivate || false,
    tags: req.body.tags || []
  };
  postClient.CreatePost(data, (err, responseData) => {
    if (err) {return handleGrpcError(err, res);}
    // Успешно
    return res.status(201).json(responseData.post);
  });
});

apiGateway.get('/posts/:id', verifyToken, (req, res) => {
  const postId = req.params.id;
  postClient.GetPost({ id: postId }, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.json(responseData.post);
  });
});

apiGateway.put('/posts/:id', verifyToken, (req, res) => {
  const postId = req.params.id;
  const data = {
    title: req.body.title,
    description: req.body.description,
    creatorId: postId, // используем postId, потому что так в .proto
    isPrivate: req.body.isPrivate || false,
    tags: req.body.tags || []
  };
  postClient.UpdatePost(data, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.json(responseData.post);
  });
});

apiGateway.delete('/posts/:id', verifyToken, (req, res) => {
  const postId = req.params.id;
  postClient.DeletePost({ id: postId }, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.json(responseData.post);
  });
});

apiGateway.get('/posts', verifyToken, (req, res) => {
  const page = parseInt(req.query.page || '1', 10);
  const pageSize = parseInt(req.query.pageSize || '10', 10);
  postClient.ListPosts({ page, pageSize }, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.json({
      posts: responseData.posts,
      totalCount: responseData.totalCount
    });
  });
});


function handleGrpcError(err, res) {
  switch (err.code) {
    case grpc.status.NOT_FOUND:
      return res.status(404).json({ error: 'Not Found' });
    case grpc.status.INVALID_ARGUMENT:
      return res.status(400).json({ error: 'Invalid argument' });
    default:
      return res.status(500).json({ error: err.details });
  }
}
apiGateway.post('/posts/:id/view', verifyToken, async (req, res) => {
  const postId   = req.params.id;
  const clientId = req.userId;
  const viewedAt = new Date().toISOString();
  const msg      = { postId, clientId, timestamp: viewedAt };

  try {
    await producer.send({
      topic: 'post-views',
      messages: [{ value: JSON.stringify(msg) }]
    });

  } catch (e) {
    return res.status(500).json({ error: 'Kafka error: ' + e.message });
  }

  postClient.ViewPost(msg, (err, response) => {
    if (err) return handleGrpcError(err, res);
    if (!response || !response.post) {
      return res.status(502).json({ error: 'Invalid gRPC response' });
    }
    const post = response.post;
    return res.json({ ...post, viewedAt });
  });
});

apiGateway.post('/posts/:id/like', verifyToken, async (req, res) => {
  const postId   = req.params.id;
  const clientId = req.userId;
  // отметка времени лайка
  const likedAt  = new Date().toISOString();
  const msg      = { postId, clientId, timestamp: likedAt };

  // 1) шлём в Kafka
  try {
    await producer.send({
      topic: 'post-likes',
      messages: [{ value: JSON.stringify(msg) }]
    });
  } catch (e) {
    return res.status(500).json({ error: 'Kafka error: ' + e.message });
  }

  // 2) вызываем gRPC и возвращаем вместе с likedAt
  postClient.LikePost(msg, (err, response) => {
    if (err) return handleGrpcError(err, res);
    if (!response || !response.post) {
      return res.status(502).json({ error: 'Invalid gRPC response' });
    }
    const post = response.post;
    return res.json({ ...post, likedAt });
  });
});

apiGateway.post('/posts/:id/comments', verifyToken, async (req, res) => {
  const postId   = req.params.id;
  const clientId = req.userId;
  const content  = req.body.content;
  const timestamp = new Date().toISOString();
  const msg      = { postId, clientId, content, timestamp };

  try {
    await producer.send({
      topic: 'post-comments',
      messages: [{ value: JSON.stringify(msg) }]
    });
  } catch (e) {
    return res.status(500).json({ error: 'Kafka error: ' + e.message });
  }

  postClient.AddComment(msg, (err, response) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    if (!response || !response.comment) {
      return res.status(502).json({ error: 'Invalid gRPC response' });
    }
    return res.status(201).json(response.comment);
  });
});

apiGateway.get('/posts/:id/comments', verifyToken, (req, res) => {

  const postId   = req.params.id;
  const page     = parseInt(req.query.page     || '1',  10);
  const pageSize = parseInt(req.query.pageSize || '10', 10);
  const reqMsg   = { postId, page, pageSize };

  postClient.ListComments(reqMsg, (err, response) => {

    if (err) {
      return handleGrpcError(err, res);
    }

    if (!response || !Array.isArray(response.comments)) {
      return res.status(502).json({ error: 'Invalid gRPC response' });
    }

    return res.json({
      comments:    response.comments,
      totalCount: response.totalCount
    });

  });
});

apiGateway.get('/', (req, res) => {
  res.send('Main API up');
});

const PORT = process.env.PORT || 3000;
apiGateway.listen(PORT, () => {
  console.log(`Main API on port ${PORT}`);
});