import time
import uuid
from datetime import datetime
from concurrent import futures
from kafka import KafkaProducer
import json
import grpc
import content_pb2
import content_pb2_grpc
from kafka.errors import NoBrokersAvailable


class ContentStorage:
    def __init__(self):
        self.content_db = {}
        self.feedback_db = {}


class ContentService(content_pb2_grpc.ContentHandlerServicer):
    def __init__(self):
        self.storage = ContentStorage()
        self.event_producer = self._create_event_producer()

    def _create_event_producer(self):
        retries = 0
        while True:
            try:
                return KafkaProducer(
                    bootstrap_servers=["kafka:9092"],
                    value_serializer=lambda v: json.dumps(v).encode(),
                )
            except NoBrokersAvailable:
                retries += 1
                if retries > 30:
                    raise RuntimeError("Event broker unavailable")
                time.sleep(2)

    def RecordView(self, request, context):
        self._send_event('content-views', {
            'contentId': request.contentId,
            'userId': request.userId,
            'timestamp': datetime.utcnow().isoformat()
        })
        return self.GetContent(
            content_pb2.ContentId(id=request.contentId),
            context
        )

    def RecordLike(self, request, context):
        self._send_event('content-likes', {
            'contentId': request.contentId,
            'userId': request.userId,
            'timestamp': datetime.utcnow().isoformat()
        })
        return self.GetContent(
            content_pb2.ContentId(id=request.contentId),
            context
        )

    def AddFeedback(self, request, context):
        feedback_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        feedback = {
            'id': feedback_id,
            'contentId': request.contentId,
            'userId': request.userId,
            'message': request.message,
            'createdAt': now
        }
        self.storage.feedback_db.setdefault(request.contentId, []).append(feedback)
        self._send_event('content-feedback', feedback)
        return content_pb2.FeedbackResponse(
            feedback=self._feedback_to_proto(feedback)
        )

    def ListFeedback(self, request, context):
        all_feedback = self.storage.feedback_db.get(request.contentId, [])
        total = len(all_feedback)
        page = max(request.page, 1)
        size = max(request.limit, 1)
        start = (page - 1) * size
        slice_ = all_feedback[start:start + size]
        return content_pb2.FeedbackList(
            feedback=[self._feedback_to_proto(f) for f in slice_],
            count=total
        )

    def _feedback_to_proto(self, feedback):
        return content_pb2.Feedback(
            id=feedback["id"],
            contentId=feedback["contentId"],
            userId=feedback["userId"],
            message=feedback["message"],
            createdAt=feedback["createdAt"],
        )

    def CreateContent(self, request, context):
        content_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        data = {
            "id": content_id,
            "title": request.title,
            "description": request.description,
            "authorId": request.authorId,
            "isRestricted": request.isRestricted,
            "categories": list(request.categories),
            "createdAt": now,
            "updatedAt": now
        }
        self.storage.content_db[content_id] = data
        return content_pb2.ContentResponse(content=self._content_to_proto(data))

    def GetContent(self, request, context):
        if request.id not in self.storage.content_db:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Content not found")
            return content_pb2.ContentResponse()
        data = self.storage.content_db[request.id]
        return content_pb2.ContentResponse(content=self._content_to_proto(data))

    def UpdateContent(self, request, context):
        content_id = request.authorId
        if content_id not in self.storage.content_db:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Content not found")
            return content_pb2.ContentResponse()
        now = datetime.utcnow().isoformat()
        data = self.storage.content_db[content_id]
        data["title"] = request.title
        data["description"] = request.description
        data["isRestricted"] = request.isRestricted
        data["categories"] = list(request.categories)
        data["updatedAt"] = now
        return content_pb2.ContentResponse(content=self._content_to_proto(data))

    def RemoveContent(self, request, context):
        if request.id not in self.storage.content_db:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Content not found")
            return content_pb2.ContentResponse()
        deleted = self.storage.content_db.pop(request.id)
        return content_pb2.ContentResponse(content=self._content_to_proto(deleted))

    def ListContent(self, request, context):
        page = request.page if request.page >= 1 else 1
        limit = request.limit if request.limit > 0 else 10
        all_content = list(self.storage.content_db.values())
        total = len(all_content)
        start = (page - 1) * limit
        end = start + limit
        slice_ = all_content[start:end]
        content_list = [self._content_to_proto(d) for d in slice_]
        return content_pb2.ContentList(items=content_list, count=total)

    def _content_to_proto(self, data):
        return content_pb2.Content(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            authorId=data["authorId"],
            isRestricted=data["isRestricted"],
            categories=data["categories"],
            createdAt=data["createdAt"],
            updatedAt=data["updatedAt"]
        )

    def _send_event(self, topic, data):
        self.event_producer.send(topic, data)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    content_pb2_grpc.add_ContentHandlerServicer_to_server(ContentService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Content Service running on port 50051...")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()