from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(db.Boolean, default=True)

    tutor_info = db.relationship('TutorInfo', backref='user', uselist=False, cascade='all, delete-orphan')
    student_info = db.relationship('StudentInfo', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class TutorInfo(db.Model):
    __tablename__ = 'tutor_infos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    avatar_path = db.Column(db.String(255))
    subjects = db.Column(db.String(100), nullable=False)
    grades = db.Column(db.String(100), nullable=False)
    teaching_mode = db.Column(db.String(50), nullable=False)
    fee = db.Column(db.Integer, nullable=False)
    teaching_time = db.Column(db.Text)
    introduction = db.Column(db.String(50), nullable=False)
    wechat = db.Column(db.String(50))
    accept_opposite_gender = db.Column(db.Boolean, default=True)
    listing_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

class StudentInfo(db.Model):
    __tablename__ = 'student_infos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    avatar_path = db.Column(db.String(255))
    subjects = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(20), nullable=False)
    teaching_mode = db.Column(db.String(50), nullable=False)
    budget_upper = db.Column(db.Integer)
    teaching_time = db.Column(db.Text)
    requirements = db.Column(db.String(50))
    wechat = db.Column(db.String(50))
    accept_opposite_gender = db.Column(db.Boolean, default=False)
    listing_active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    target_role = db.Column(db.String(20), nullable=False)
    target_profile_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('user_id', 'target_role', 'target_profile_id', name='uq_favorite_unique_target'),
    )

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tutor_id = db.Column(db.Integer, db.ForeignKey('tutor_infos.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    student = db.relationship('User', backref='reviews_given')
    tutor = db.relationship('TutorInfo', backref='reviews_received')

    __table_args__ = (
        UniqueConstraint('student_id', 'tutor_id', name='uq_review_unique'),
    )
