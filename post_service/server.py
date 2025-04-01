import time
import uuid
from datetime import datetime
from concurrent import futures

import grpc
import posts_pb2
import posts_pb2_grpc

# Хранилище промокодов (в памяти)
PROMOS_DB = {}  # { promo_id: {...}, ... }

class PromoServiceServicer(posts_pb2_grpc.PromoServiceServicer):
    def CreatePromo(self, request, context):
        promo_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        data = {
            "id": promo_id,
            "title": request.title,
            "description": request.description,
            "creatorId": request.creatorId,
            "discountSize": request.discountSize,
            "code": request.code,
            "createdAt": now,
            "updatedAt": now
        }
        PROMOS_DB[promo_id] = data
        return posts_pb2.PromoResponse(promo=self._dict_to_promo(data))

    def GetPromo(self, request, context):
        if request.id not in PROMOS_DB:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Promo not found")
            return posts_pb2.PromoResponse()
        data = PROMOS_DB[request.id]
        return posts_pb2.PromoResponse(promo=self._dict_to_promo(data))

    def UpdatePromo(self, request, context):
        # Здесь в запросе используем creatorId для передачи идентификатора промокода
        promo_id = request.creatorId
        if promo_id not in PROMOS_DB:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Promo not found")
            return posts_pb2.PromoResponse()
        now = datetime.utcnow().isoformat()
        data = PROMOS_DB[promo_id]
        data["title"] = request.title
        data["description"] = request.description
        data["discountSize"] = request.discountSize
        data["code"] = request.code
        data["updatedAt"] = now
        return posts_pb2.PromoResponse(promo=self._dict_to_promo(data))

    def DeletePromo(self, request, context):
        if request.id not in PROMOS_DB:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Promo not found")
            return posts_pb2.PromoResponse()
        deleted = PROMOS_DB.pop(request.id)
        return posts_pb2.PromoResponse(promo=self._dict_to_promo(deleted))

    def ListPromos(self, request, context):
        page = request.page if request.page >= 1 else 1
        page_size = request.pageSize if request.pageSize > 0 else 10
        all_promos = list(PROMOS_DB.values())
        total_count = len(all_promos)
        start = (page - 1) * page_size
        end = start + page_size
        slice_ = all_promos[start:end]
        promos = [self._dict_to_promo(p) for p in slice_]
        return posts_pb2.ListPromosResponse(promos=promos, totalCount=total_count)

    def _dict_to_promo(self, d):
        return posts_pb2.Promo(
            id=d["id"],
            title=d["title"],
            description=d["description"],
            creatorId=d["creatorId"],
            discountSize=d["discountSize"],
            code=d["code"],
            createdAt=d["createdAt"],
            updatedAt=d["updatedAt"]
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    posts_pb2_grpc.add_PromoServiceServicer_to_server(PromoServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("PromoService gRPC running on port 50051...")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()