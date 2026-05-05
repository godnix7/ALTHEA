from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from .models import User, LoginLog
from werkzeug.security import generate_password_hash, check_password_hash
from . import db   ##means from __init__.py import db
from flask_login import login_user, login_required, logout_user, current_user


auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user:
            if user.is_banned:
                flash('Your account has been suspended. Contact support for reinstatement.', category='error')
                return render_template("login.html", user=current_user)
            if check_password_hash(user.password, password):
                # Promote to admin if email matches admin list
                admin_emails = current_app.config.get('ADMIN_EMAILS', [])
                if email in admin_emails and not user.is_admin:
                    user.is_admin = True
                    db.session.commit()
                    # Refresh user object to get updated is_admin status
                    db.session.refresh(user)
                
                flash('Logged in successfully!', category='success')
                login_user(user, remember=True)
                login_log = LoginLog(user_id=user.id, action='login')
                db.session.add(login_log)
                db.session.commit()
                # Redirect admins to admin dashboard, others to home
                if user.is_admin:
                    return redirect(url_for('views.admin_dashboard'))
                return redirect(url_for('views.home'))
            else:
                flash('Incorrect password, try again.', category='error')
        else:
            flash('Email does not exist.', category='error')

    return render_template("login.html", user=current_user)


@auth.route('/logout')
@login_required
def logout():
    login_log = LoginLog(user_id=current_user.id, action='logout')
    db.session.add(login_log)
    db.session.commit()
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        first_name = (request.form.get('firstName') or '').strip()
        username = (request.form.get('username') or first_name or '').strip()
        password1 = request.form.get('password1')
        password2 = request.form.get('password2')

        user = User.query.filter_by(email=email).first()
        username_taken = User.query.filter_by(username=username).first() if username else None
        if user:
            flash('Email already exists.', category='error')
        elif username_taken:
            flash('Username already exists. Please choose another.', category='error')
        elif len(email) < 4:
            flash('Email must be greater than 3 characters.', category='error')
        elif len(username) < 2:
            flash('Display name must be at least 2 characters.', category='error')
        elif password1 != password2:
            flash('Passwords don\'t match.', category='error')
        elif len(password1) < 7:
            flash('Password must be at least 7 characters.', category='error')
        else:
            admin_emails = current_app.config.get('ADMIN_EMAILS', [])
            new_user = User(
                email=email,
                first_name=first_name or username,
                username=username or first_name or email.split('@')[0],
                password=generate_password_hash(password1, method='pbkdf2:sha256'),
                is_admin=email in admin_emails,
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user, remember=True)
            login_log = LoginLog(user_id=new_user.id, action='login')
            db.session.add(login_log)
            db.session.commit()
            flash('Account created!', category='success')
            # Redirect admins to admin dashboard, others to home
            if new_user.is_admin:
                return redirect(url_for('views.admin_dashboard'))
            return redirect(url_for('views.home'))

    return render_template("sign_up.html", user=current_user)
