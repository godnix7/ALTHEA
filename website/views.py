import base64
import json
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    jsonify,
    redirect,
    url_for,
    current_app,
    abort,
)
from flask_login import login_required, current_user
from sqlalchemy import func

from . import db
from .agent import get_agent
from .models import Note, LoginLog, ChatMessage, GAD9Result, User, ChatSession
from .voice import synthesize_speech, transcribe_audio, VoiceServiceError

views = Blueprint('views', __name__)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def _guard_banned_user():
    if current_user.is_authenticated and current_user.is_banned:
        flash(
            'Your account is currently banned. Contact support for assistance.',
            category='error',
        )
        return redirect(url_for('views.help_page'))


def _generate_session_title(user):
    timestamp = datetime.utcnow().strftime('%b %d • %I:%M %p')
    return f"{user.display_name()}'s chat ({timestamp})"


def _start_chat_session(user, title=None, activate_existing=True):
    if activate_existing:
        ChatSession.query.filter_by(user_id=user.id, is_active=True).update(
            {'is_active': False}
        )
    session = ChatSession(
        user_id=user.id,
        title=title or _generate_session_title(user),
        is_active=True,
    )
    db.session.add(session)
    db.session.commit()
    return session


@views.route('/', methods=['GET'])
@login_required
def home():
    if current_user.is_banned:
        return _guard_banned_user()
    return redirect(url_for('views.chat'))


@views.route('/overview', methods=['GET'])
def overview():
    return render_template("overview.html")


@views.route('/mentor', methods=['GET'])
def mentor():
    return render_template("mentor.html")


@views.route('/help', methods=['GET'])
def help_page():
    help_email = current_app.config.get('HELP_EMAIL', 'nischaykademane@gmail.com')
    return render_template("help.html", help_email=help_email)


@views.route('/terms', methods=['GET'])
def terms():
    return render_template("terms.html")


@views.route('/chat')
@login_required
def chat():
    if current_user.is_banned:
        return _guard_banned_user()

    latest_result = (
        GAD9Result.query.filter_by(user_id=current_user.id)
        .order_by(GAD9Result.created_at.desc())
        .first()
    )
    active_session = _start_chat_session(current_user)

    return render_template(
        "index.html",
        user=current_user,
        gad9_result=latest_result,
        active_session=active_session,
        help_email=current_app.config.get('HELP_EMAIL'),
        ai_settings={
            'active_provider': current_user.active_ai_provider,
            'has_openai': bool(current_user.openai_api_key),
            'has_gemini': bool(current_user.gemini_api_key),
            'has_anthropic': bool(current_user.anthropic_api_key)
        }
    )



@views.route('/chat/messages', methods=['GET', 'POST'])
@login_required
def chat_messages():
    if current_user.is_banned:
        return jsonify({'error': 'Account banned. Contact support.'}), 403
    latest_result = (
        GAD9Result.query.filter_by(user_id=current_user.id)
        .order_by(GAD9Result.created_at.desc())
        .first()
    )

    if request.method == 'GET':
        session_id = request.args.get('session_id', type=int)
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400

        session = ChatSession.query.filter_by(
            id=session_id, user_id=current_user.id
        ).first_or_404()
        messages = (
            ChatMessage.query.filter_by(session_id=session.id)
            .order_by(ChatMessage.timestamp.asc())
            .all()
        )
        return jsonify([message.to_dict() for message in messages])

    data = request.get_json() or {}
    text = (data.get('message') or '').strip()
    session_id = data.get('session_id')
    input_mode = (data.get('input_mode') or 'text').lower()
    response_mode = (data.get('response_mode') or 'text').lower()

    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400

    if not text:
        return jsonify({'error': 'Message is required.'}), 400

    session = ChatSession.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first()

    if not session:
        return jsonify({'error': 'Session not found.'}), 404
    if session.is_archived:
        return jsonify({'error': 'This chat is archived.'}), 400

    # Get recent conversation history for context (last 10 messages)
    recent_messages = (
        ChatMessage.query.filter_by(user_id=current_user.id, session_id=session.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(10)
        .all()
    )
    
    # Convert to dict format for agent (reverse to get chronological order)
    conversation_history = [
        {
            'sender': msg.sender,
            'message': msg.message,
        }
        for msg in reversed(recent_messages)
    ]

    user_message = ChatMessage(
        user_id=current_user.id,
        session_id=session.id,
        sender='user',
        message=text,
        input_mode=input_mode,
        response_mode=response_mode,
    )
    db.session.add(user_message)
    db.session.flush()

    # Use the MH Agent to generate response
    error_detail = None
    try:
        agent = get_agent()
        gad9_level = latest_result.level if latest_result else None
        print(f"[DEBUG] Generating response for: {text[:50]}...")
        print(f"[DEBUG] GAD-9 level: {gad9_level}")
        print(f"[DEBUG] Conversation history length: {len(conversation_history)}")
        
        agent_response = agent.generate_response(
            user_message=text,
            gad9_level=gad9_level,
            conversation_history=conversation_history,
            provider=current_user.active_ai_provider,
            api_keys={
                'openai': current_user.openai_api_key,
                'gemini': current_user.gemini_api_key,
                'anthropic': current_user.anthropic_api_key
            }
        )

        bot_reply_text = (agent_response.get('text') or '').strip()
        provider = agent_response.get('provider') or 'fallback'
        error_detail = agent_response.get('error')

        print(f"[DEBUG] Generated response: {bot_reply_text[:100]}...")

        if not bot_reply_text:
            print("[WARNING] Agent returned empty response, using fallback")
            bot_reply_text = "I'm here to listen. Could you tell me more about what you're experiencing?"
            provider = 'fallback'
    except Exception as e:
        print(f"[ERROR] Agent failed: {e}")
        import traceback
        traceback.print_exc()
        # Fallback response
        bot_reply_text = "I'm having trouble processing that right now. Could you try rephrasing your message?"
    
        provider = 'fallback'
        error_detail = str(e)
    
    bot_message = ChatMessage(
        user_id=current_user.id,
        session_id=session.id,
        sender='bot',
        message=bot_reply_text,
        input_mode=input_mode,
        response_mode=response_mode,
        provider=provider,
    )
    db.session.add(bot_message)
    session.last_preview = bot_reply_text[:180] or text[:180]
    session.updated_at = func.now()
    db.session.commit()

    return jsonify(
        {
            'messages': [
                {
                    'id': user_message.id,
                    'sender': user_message.sender,
                    'message': user_message.message,
                    'timestamp': user_message.timestamp.isoformat()
                    if user_message.timestamp
                    else None,
                    'session_id': session.id,
                    'input_mode': user_message.input_mode,
                },
                {
                    'id': bot_message.id,
                    'sender': bot_message.sender,
                    'message': bot_message.message,
                    'timestamp': bot_message.timestamp.isoformat()
                    if bot_message.timestamp
                    else None,
                    'provider': bot_message.provider,
                    'session_id': session.id,
                    'response_mode': bot_message.response_mode,
                },
            ],
            'meta': {
                'provider': bot_message.provider,
                'error': error_detail,
            },
        }
    )


@views.route('/chat/session', methods=['POST'])
@login_required
def create_chat_session():
    if current_user.is_banned:
        return jsonify({'error': 'Account banned. Contact support.'}), 403

    data = request.get_json() or {}
    title = (data.get('title') or '').strip() or None
    session = _start_chat_session(current_user, title=title)
    return jsonify(session.to_dict())


@views.route('/account')
@login_required
def account():
    login_history = (
        LoginLog.query.filter_by(user_id=current_user.id)
        .order_by(LoginLog.timestamp.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "account.html",
        user=current_user,
        login_history=login_history,
    )


@views.route('/update-ai-keys', methods=['POST'])
@login_required
def update_ai_keys():
    openai_key = request.form.get('openai_api_key')
    gemini_key = request.form.get('gemini_api_key')
    anthropic_key = request.form.get('anthropic_api_key')
    active_provider = request.form.get('active_ai_provider')

    current_user.openai_api_key = openai_key
    current_user.gemini_api_key = gemini_key
    current_user.anthropic_api_key = anthropic_key
    current_user.active_ai_provider = active_provider

    db.session.commit()
    flash('AI settings updated successfully!', category='success')
    return redirect(url_for('views.account'))



@views.route('/chat/history')
@login_required
def chat_history():
    if current_user.is_banned:
        return _guard_banned_user()

    sessions = (
        ChatSession.query.filter_by(user_id=current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    return render_template(
        "chat_history.html",
        user=current_user,
        sessions=sessions,
    )


@views.route('/chat/history/<int:session_id>')
@login_required
def chat_history_detail(session_id: int):
    if current_user.is_banned:
        return _guard_banned_user()

    session = ChatSession.query.filter_by(
        id=session_id, user_id=current_user.id
    ).first_or_404()
    messages = (
        ChatMessage.query.filter_by(session_id=session.id)
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )
    return render_template(
        "chat_history_detail.html",
        user=current_user,
        session=session,
        messages=messages,
    )


@views.route('/gad9')
@login_required
def gad9():
    return render_template("gad9.html", user=current_user)


@views.route('/gad9/result', methods=['POST'])
@login_required
def gad9_result():
    data = request.get_json() or {}
    score = data.get('score')
    level = data.get('level')
    answers = data.get('answers')

    if score is None or level is None:
        return jsonify({'error': 'Score and level are required.'}), 400

    try:
        result = GAD9Result(
            user_id=current_user.id,
            score=int(score),
            level=str(level),
            answers=json.dumps(answers) if answers is not None else None,
        )
        db.session.add(result)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': 'Failed to save result.'}), 500

    return jsonify({'status': 'ok'})


@views.route('/notes', methods=['GET', 'POST'])
@login_required
def notes():
    if request.method == 'POST':
        note = request.form.get('note')

        if not note or len(note.strip()) < 1:
            flash('Note is too short!', category='error')
        else:
            new_note = Note(data=note, user_id=current_user.id)
            db.session.add(new_note)
            db.session.commit()
            flash('Note added!', category='success')

    notes = Note.query.filter_by(user_id=current_user.id).all()
    return render_template("home.html", user=current_user, notes=notes)


@views.route('/delete-note', methods=['POST'])
def delete_note():  
    note = json.loads(request.data) # this function expects a JSON from the INDEX.js file 
    noteId = note['noteId']
    note = Note.query.get(noteId)
    if note:
        if note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()

    return jsonify({})


@views.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'total_users': User.query.count(),
        'active_chats': ChatSession.query.filter_by(is_active=True).count(),
        'banned_users': User.query.filter_by(is_banned=True).count(),
        'total_messages': ChatMessage.query.count(),
    }
    users = User.query.order_by(User.created_at.desc()).all()
    banned_users = [user for user in users if user.is_banned]
    recent_sessions = (
        ChatSession.query.order_by(ChatSession.updated_at.desc())
        .limit(15)
        .all()
    )
    return render_template(
        "admin_dashboard.html",
        user=current_user,
        stats=stats,
        users=users,
        banned_users=banned_users,
        sessions=recent_sessions,
    )


@views.route('/admin/users/<int:user_id>/toggle-ban', methods=['POST'])
@login_required
@admin_required
def toggle_ban(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': "You can't change your own ban status."}), 400

    data = request.get_json() or {}
    action = data.get('action')
    reason = (data.get('reason') or '').strip() or 'Manual action'

    if action == 'ban':
        user.is_banned = True
        user.ban_reason = reason
        user.banned_at = datetime.utcnow()
    elif action == 'unban':
        user.is_banned = False
        user.ban_reason = None
        user.banned_at = None
    else:
        return jsonify({'error': 'Unknown action'}), 400

    db.session.commit()
    return jsonify(
        {
            'status': 'ok',
            'user': {
                'id': user.id,
                'username': user.display_name(),
                'email': user.email,
                'is_banned': user.is_banned,
                'ban_reason': user.ban_reason,
            },
        }
    )


@views.route('/admin/chats/<int:session_id>')
@login_required
@admin_required
def admin_chat_detail(session_id: int):
    session = ChatSession.query.get_or_404(session_id)
    owner = User.query.get(session.user_id)
    messages = (
        ChatMessage.query.filter_by(session_id=session.id)
        .order_by(ChatMessage.timestamp.asc())
        .all()
    )
    return render_template(
        "admin_chat_detail.html",
        user=current_user,
        session=session,
        owner=owner,
        messages=messages,
    )


@views.route('/api/voice/speak', methods=['POST'])
@login_required
def api_voice_speak():
    if current_user.is_banned:
        return jsonify({'error': 'Account banned.'}), 403

    data = request.get_json() or {}
    text_value = (data.get('text') or '').strip()
    voice = (data.get('voice') or 'alloy').strip()

    if not text_value:
        return jsonify({'error': 'Text is required.'}), 400

    try:
        audio_bytes, mime_type = synthesize_speech(text_value, voice=voice)
        payload = base64.b64encode(audio_bytes).decode('utf-8')
        return jsonify({'audio': payload, 'mime': mime_type})
    except VoiceServiceError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception:
        return jsonify({'error': 'Unable to generate speech audio.'}), 500


@views.route('/api/voice/transcribe', methods=['POST'])
@login_required
def api_voice_transcribe():
    if current_user.is_banned:
        return jsonify({'error': 'Account banned.'}), 403

    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'Audio file is required.'}), 400

    try:
        text_value = transcribe_audio(audio_file)
        return jsonify({'text': text_value})
    except VoiceServiceError as exc:
        return jsonify({'error': str(exc)}), 503
    except Exception:
        return jsonify({'error': 'Unable to transcribe audio.'}), 500
