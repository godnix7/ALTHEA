import os
from datetime import datetime

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()
DB_NAME = "database.db"
USERS_DB_NAME = "users.db"


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hjshjhdjah kjshkjdhjs'
    app.config['HELP_EMAIL'] = os.getenv('HELP_EMAIL', 'nischaykademane@gmail.com')
    admin_emails = os.getenv('ADMIN_EMAILS', 'nischaykademane2006@gmail.com')
    app.config['ADMIN_EMAILS'] = [
        email.strip().lower() for email in admin_emails.split(',') if email.strip()
    ]
    os.makedirs(app.instance_path, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(app.instance_path, DB_NAME)}"
    app.config['SQLALCHEMY_BINDS'] = {
        'users': f"sqlite:///{os.path.join(app.instance_path, USERS_DB_NAME)}"
    }
    db.init_app(app)

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    from .models import (
        User,
        Note,
        LoginLog,
        ChatMessage,
        GAD9Result,
        ChatSession,
    )

    with app.app_context():
        db.create_all()
        db.create_all(bind_key='users')
        _ensure_schema(app)
        _backfill_missing_sessions()
        _promote_configured_admins(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    return app


def _ensure_schema(app: Flask):
    """Ensure new columns exist when running without Alembic."""
    engine = db.get_engine(app, bind='users')
    inspector = inspect(engine)

    def ensure_column(table: str, column: str, ddl: str):
        columns = {col['name'] for col in inspector.get_columns(table)}
        if column in columns:
            return

        statement = text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        with engine.begin() as connection:
            connection.execute(statement)

    ensure_column('user', 'username', 'VARCHAR(150)')
    ensure_column('user', 'is_admin', 'BOOLEAN NOT NULL DEFAULT 0')
    ensure_column('user', 'is_banned', 'BOOLEAN NOT NULL DEFAULT 0')
    ensure_column('user', 'ban_reason', 'VARCHAR(255)')
    ensure_column('user', 'banned_at', 'DATETIME')
    ensure_column('user', 'phone_number', 'VARCHAR(20)')
    ensure_column('user', 'created_at', 'DATETIME')
    ensure_column('user', 'updated_at', 'DATETIME')
    ensure_column('chat_message', 'session_id', 'INTEGER')
    ensure_column('chat_message', 'input_mode', "VARCHAR(20) DEFAULT 'text'")
    ensure_column('chat_message', 'response_mode', "VARCHAR(20) DEFAULT 'text'")
    ensure_column('chat_message', 'provider', "VARCHAR(50) DEFAULT 'ollama'")
    ensure_column('user', 'openai_api_key', 'VARCHAR(255)')
    ensure_column('user', 'gemini_api_key', 'VARCHAR(255)')
    ensure_column('user', 'anthropic_api_key', 'VARCHAR(255)')
    ensure_column('user', 'active_ai_provider', "VARCHAR(50) DEFAULT 'ollama'")



def _backfill_missing_sessions():
    """Create chat sessions for legacy chat messages that lack one."""
    from .models import ChatMessage, ChatSession, User

    users = User.query.all()
    for user in users:
        legacy_messages = (
            ChatMessage.query.filter_by(user_id=user.id, session_id=None)
            .order_by(ChatMessage.timestamp.asc())
            .all()
        )
        if not legacy_messages:
            continue

        first_timestamp = legacy_messages[0].timestamp or datetime.utcnow()
        title = f"Conversation {first_timestamp.strftime('%b %d %H:%M')}"
        session = ChatSession(
            user_id=user.id,
            title=title,
            last_preview=legacy_messages[0].message[:120],
            is_active=False,
        )
        db.session.add(session)
        db.session.flush()

        for message in legacy_messages:
            message.session_id = session.id
        session.updated_at = legacy_messages[-1].timestamp or datetime.utcnow()
        db.session.commit()


def _promote_configured_admins(app: Flask):
    from .models import User

    configured = {email for email in app.config.get('ADMIN_EMAILS', [])}
    if not configured:
        return

    updates = False
    for email in configured:
        user = User.query.filter_by(email=email).first()
        if user and not user.is_admin:
            user.is_admin = True
            updates = True
    if updates:
        db.session.commit()



