const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const path = require('path');
const protoLoader = require('@grpc/proto-loader');
const grpc = require('@grpc/grpc-js');

const apiGateway = express();
apiGateway.use(express.json());

const USER_MICROSERVICE_URL = process.env.USER_MICROSERVICE_URL || 'http://user_service:5001';
const AUTH_SECRET = process.env.AUTH_SECRET || 'ultra-secure-key';
const POST_MICROSERVICE_HOST = process.env.POST_MICROSERVICE_HOST || 'content_service:50051';

const PROTO_FILE_PATH = path.join(__dirname, 'content.proto');
const protoConfig = protoLoader.loadSync(PROTO_FILE_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true
});
const protoDescriptor = grpc.loadPackageDefinition(protoConfig);
const contentService = protoDescriptor.content;

const contentClient = new contentService.ContentHandler(
  POST_MICROSERVICE_HOST,
  grpc.credentials.createInsecure()
);

const { Kafka } = require('kafkajs');
const kafkaBroker = new Kafka({ brokers: ['kafka:9092'] });
const eventProducer = kafkaBroker.producer();

(async () => {
  await eventProducer.connect();
})();

function authenticateRequest(req, res, next) {
  const authHeader = req.headers['authorization'];
  if (!authHeader) {
    return res.status(401).json({ error: 'Authorization header missing' });
  }
  const token = authHeader.split(' ')[1];
  if (!token) {
    return res.status(401).json({ error: 'Malformed token' });
  }
  try {
    const decoded = jwt.verify(token, AUTH_SECRET);
    req.userId = decoded.sub;
    next();
  } catch (err) {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

apiGateway.post('/users/signup', async (req, res) => {
  try {
    const response = await axios.post(`${USER_MICROSERVICE_URL}/users/register`, req.body, {
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

apiGateway.get('/users/account', authenticateRequest, async (req, res) => {
  try {
    const response = await axios.get(
      `${USER_MICROSERVICE_URL}/users/profile`,
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

apiGateway.put('/users/account', authenticateRequest, async (req, res) => {
  try {
    const response = await axios.put(
      `${USER_MICROSERVICE_URL}/users/profile`,
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

apiGateway.post('/users/auth', async (req, res) => {
  try {
    const response = await axios.post(`${USER_MICROSERVICE_URL}/users/login`, req.body, {
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

apiGateway.post('/content', authenticateRequest, (req, res) => {
  const contentData = {
    title: req.body.title,
    description: req.body.description,
    authorId: req.userId,
    isRestricted: req.body.isPrivate || false,
    categories: req.body.tags || []
  };
  contentClient.CreateContent(contentData, (err, response) => {
    if (err) {return handleServiceError(err, res);}
    return res.status(201).json(response.content);
  });
});

apiGateway.get('/content/:id', authenticateRequest, (req, res) => {
  const contentId = req.params