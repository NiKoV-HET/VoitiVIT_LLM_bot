import base64
import io
import os
import uuid
from datetime import timedelta

from minio import Minio
from minio.error import S3Error
from PIL import Image

# Инициализация клиента Minio
minio_client = Minio(
    f"{os.getenv('MINIO_HOST')}:{os.getenv('MINIO_PORT')}",
    access_key=os.getenv("MINIO_ROOT_USER"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
    secure=False,  # Используем HTTP вместо HTTPS для локальной разработки
)

# Имя бакета для хранения изображений
BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "user-images")


async def init_minio():
    """Инициализация Minio: создание бакета, если он не существует"""
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
            print(f"Bucket '{BUCKET_NAME}' created successfully")
        else:
            print(f"Bucket '{BUCKET_NAME}' already exists")
    except S3Error as err:
        print(f"Error initializing Minio: {err}")


async def save_image(image_data: bytes, user_id: str) -> str:
    """
    Сохраняет изображение в Minio
    
    Args:
        image_data: Байты изображения
        user_id: ID пользователя
        
    Returns:
        Путь к сохраненному изображению
    """
    try:
        # Генерируем уникальное имя файла
        random_suffix = uuid.uuid4().hex[:8]
        file_name = f"{user_id}_{random_suffix}.jpg"
        
        # Создаем объект в Minio
        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=file_name,
            data=io.BytesIO(image_data),
            length=len(image_data),
            content_type="image/jpeg"
        )
        
        return file_name
    except S3Error as err:
        print(f"Error saving image to Minio: {err}")
        raise


async def get_image(image_path: str) -> bytes:
    """
    Получает изображение из Minio
    
    Args:
        image_path: Путь к изображению
        
    Returns:
        Байты изображения
    """
    try:
        response = minio_client.get_object(BUCKET_NAME, image_path)
        return response.read()
    except S3Error as err:
        print(f"Error getting image from Minio: {err}")
        raise
    finally:
        response.close()
        response.release_conn()


async def get_image_url(image_path: str) -> str:
    """
    Получает временную URL для доступа к изображению
    
    Args:
        image_path: Путь к изображению
        
    Returns:
        Временная URL для доступа к изображению
    """
    try:
        url = minio_client.presigned_get_object(
            bucket_name=BUCKET_NAME,
            object_name=image_path,
            expires=timedelta(hours=1)
        )
        return url
    except S3Error as err:
        print(f"Error getting image URL from Minio: {err}")
        raise


async def image_to_base64(image_path: str) -> str:
    """
    Конвертирует изображение в base64
    
    Args:
        image_path: Путь к изображению
        
    Returns:
        Строка base64
    """
    try:
        image_data = await get_image(image_path)
        encoded_image = base64.b64encode(image_data).decode('utf-8')
        return encoded_image
    except Exception as err:
        print(f"Error converting image to base64: {err}")
        raise 