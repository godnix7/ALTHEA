from datetime import datetime

from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Note(db.Model, TimestampMixin):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10000))
    date = db.Column(db.DateTime(timezone=True), default=func.now())
    user_id = db.Column(db.Integer, nullable=False, index=True)


class LoginLog(db.Model):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())


class User(db.Model, UserMixin, TimestampMixin):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    username = db.Column(db.String(150), unique=True, nullable=True)
    first_name = db.Column(db.String(150))
    phone_number = db.Column(db.String(20))
    password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    ban_reason = db.Column(db.String(255))
    banned_at = db.Column(db.DateTime(timezone=True))
    
    # AI Agent Keys
    openai_api_key = db.Column(db.String(255))
    gemini_api_key = db.Column(db.String(255))
    anthropic_api_key = db.Column(db.String(255))
    active_ai_provider = db.Column(db.String(50), default='ollama')


    def display_name(self) -> str:
        return self.username or self.first_name or (self.email.split('@')[0] if self.email else 'User')


class ChatSession(db.Model, TimestampMixin):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    last_preview = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic')

    def to_dict(self, include_messages: bool = False):
        payload = {
            'id': self.id,
            'title': self.title,
            'last_preview': self.last_preview,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_messages:
            payload['messages'] = [
                message.to_dict()
                for message in self.messages.order_by(ChatMessage.timestamp.asc()).all()
            ]
        return payload


class ChatMessage(db.Model):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), index=True)
    sender = db.Column(db.String(10), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=func.now())
    input_mode = db.Column(db.String(20), default='text')
    response_mode = db.Column(db.String(20), default='text')
    provider = db.Column(db.String(50), default='ollama')

    def to_dict(self):
        return {
            'id': self.id,
            'sender': self.sender,
            'message': self.message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'input_mode': self.input_mode,
            'response_mode': self.response_mode,
            'provider': self.provider,
            'session_id': self.session_id,
        }


class GAD9Result(db.Model):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)
    level = db.Column(db.String(20), nullable=False)
    answers = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
