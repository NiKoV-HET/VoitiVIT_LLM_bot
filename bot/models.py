from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)  # Порядок отображения

    subtopics = relationship("Subtopic", back_populates="category")


class Subtopic(Base):
    __tablename__ = "subtopics"
    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    media = Column(String, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)  # Порядок отображения

    category = relationship("Category", back_populates="subtopics")


class User(Base):
    __tablename__ = "users"
    tg_id = Column(String, primary_key=True, nullable=False)  # Telegram ID как основной ключ
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    username = Column(String, nullable=True)
    llm_model = Column(String(255), nullable=True, default=None)  # Модель LLM для пользователя
    llm_enabled = Column(Boolean, default=True, nullable=False)  # Флаг включения LLM для пользователя


class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.tg_id"), nullable=False)  # связь с users
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.tg_id"), nullable=False)  # связь с users
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Новые модели для LLM


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    user_id = Column(String, ForeignKey("users.tg_id"), primary_key=True, nullable=False)
    used = Column(Integer, default=0, nullable=False)
    limit = Column(Integer, default=10, nullable=False)  # стандартный лимит, например 10 запросов


class LLMRequest(Base):
    __tablename__ = "llm_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.tg_id"), nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LLMConfig(Base):
    __tablename__ = "llm_config"
    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False)


# Новая модель для хранения информации о загруженных изображениях
class UserImage(Base):
    __tablename__ = "user_images"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.tg_id"), nullable=False)
    image_path = Column(String, nullable=False)  # Путь к изображению в Minio
    created_at = Column(DateTime, default=datetime.utcnow)


class LLMModel(Base):
    __tablename__ = "llm_models"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # Название модели для API
    description = Column(String, nullable=False)  # Описание модели для отображения в боте
    
    def __repr__(self):
        return f"<LLMModel(name='{self.name}', description='{self.description}')>"
