const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const path = require('path');
const protoLoader = require('@grpc/proto-loader');
const grpc = require('@grpc/grpc-js');
const app = express();

app.use(express.json());

const USER_SERVICE_URL =  process.env.USER_SERVICE_URL || 'http://user_service:5001';
const JWT_SECRET  = process.env.JWT_SECRET || 'super-secret-key';
const POST_SERVICE_HOST = process.env.POST_SERVICE_HOST || 'post_service:50051';
const PROTO_PATH = path.join(__dirname, 'posts.proto');
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true
});

const protoDescriptor = grpc.loadPackageDefinition(packageDefinition);
const postServicePackage = protoDescriptor.postservice;
const postClient = new postServicePackage.PostService(
  POST_SERVICE_HOST,
  grpc.credentials.createInsecure()
);

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

app.post('/users/register', async (req, res) => {
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

app.post('/users/login', async (req, res) => {
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

app.post('/posts', verifyToken, (req, res) => {
  const data = {
    title: req.body.title,
    description: req.body.description,
    creatorId: req.userId,
    isPrivate: req.body.isPrivate || false,
    tags: req.body.tags || []
  };
  postClient.CreatePost(data, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.status(201).json(responseData.post);
  });
});

app.get('/posts/:id', verifyToken, (req, res) => {
  const postId = req.params.id;
  postClient.GetPost({ id: postId }, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.json(responseData.post);
  });
});

app.put('/posts/:id', verifyToken, (req, res) => {
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

app.delete('/posts/:id', verifyToken, (req, res) => {
  const postId = req.params.id;
  postClient.DeletePost({ id: postId }, (err, responseData) => {
    if (err) {
      return handleGrpcError(err, res);
    }
    return res.json(responseData.post);
  });
});

app.get('/posts', verifyToken, (req, res) => {
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
    // Дополнительно можно обрабатывать PERMISSION_DENIED и т.д.
    default:
      return res.status(500).json({ error: err.details });
  }
}

app.get('/', (req, res) => {
  res.send('Main API up');
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Main API on port ${PORT}`);
});