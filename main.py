import os
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, URL
from flask_ckeditor import CKEditor, CKEditorField
from datetime import datetime
import smtplib
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from flask_gravatar import Gravatar

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ["FLASK_KEY"]
Bootstrap5(app)

# app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog.db"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///blog.db")
db = SQLAlchemy()
db.init_app(app)

ckeditor = CKEditor(app)

# initiate login manager
login_manager = LoginManager()
login_manager.init_app(app)

# footer stuff
today = datetime.today()
year = today.year
name = os.environ["MY_NAME"]

MY_EMAIL = os.environ["MY_EMAIL"]
MY_EMAIL_PASSWORD = os.environ["MY_EMAIL_PASSWORD"]
TARGET_EMAIL = os.environ["TARGET_EMAIL"]


# For adding profile images to the comment section
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:  # if a user is logged in
            if current_user.id != 1:  # and is not the admin
                return abort(403)
        else:  # random stranger
            return abort(403)
        return f(*args, **kwargs)

    return decorated_function


# CONFIGURE TABLE
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    # Create Foreign Key, "users.id" the users refers to the tablename of User.
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    # Create reference to the User object, the "posts" refers to the posts protperty in the User class.
    author = relationship("User", back_populates="posts")
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)
    # parent relationship to comments:
    comments = relationship("Comment", back_populates="parent_post")


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))
    # This will act like a List of BlogPost objects attached to each User.
    # The "author" refers to the author property in the BlogPost class.
    posts = relationship("BlogPost", back_populates="author")
    # Refers to comment_author property in Comment class
    comments = relationship("Comment", back_populates="comment_author")


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    # "users.id" The users refers to the tablename of the Users class.
    # "comments" refers to the comments property in the User class.
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")
    # child relationship to parent post:
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()


class AddPostForm(FlaskForm):
    title = StringField(label='Title', validators=[DataRequired()])
    subtitle = StringField(label='Subtitle', validators=[DataRequired()])
    date = StringField(label='Date', validators=[DataRequired()])
    body = CKEditorField(label='Body', validators=[DataRequired()])
    author = StringField(label='Author', validators=[DataRequired()])
    img_url = StringField(label='Image URL', validators=[DataRequired()])
    submit = SubmitField(label='Add Post')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/register', methods=['POST', 'GET'])
def register():
    form = RegisterForm()
    if request.method == "POST":
        email = request.form.get('email')
        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if user:
            # user already exists
            flash("Account already exists. Try logging in.")
            return redirect(url_for('login'))

        password = request.form.get('password')
        hashed_password = generate_password_hash(
            password,
            method='pbkdf2:sha256',
            salt_length=8

        )
        new_user = User(
            email=request.form.get('email'),
            password=hashed_password,
            name=request.form.get('name')
        )
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('home'))
    return render_template('register.html', form=form, current_year=year, my_name=name)


@app.route('/login', methods=['POST', 'GET'])
def login():
    form = LoginForm()
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if not user:
            flash('User does not exist.')
            return redirect(url_for('login'))

        elif not check_password_hash(user.password, password):
            flash('Incorrect password.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))

    return render_template("login.html", form=form, current_year=year, my_name=name)


@app.route('/')
def home():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", posts=posts, current_year=year, my_name=name)


@app.route("/about")
def about():
    return render_template("about.html", current_year=year, my_name=name)


@app.route('/post/<int:post_id>', methods=['POST', 'GET'])
def get_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to log in or register to comment.")
            return redirect(url_for("login"))
        new_comment = Comment(
            text=form.comment.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
        form.comment.data = ""
        redirect(url_for("get_post", post_id=post_id))
    return render_template("post.html", post=requested_post, form=form, current_year=year, my_name=name)


@app.route('/delete/<int:post_id>')
@admin_only
def delete_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for("home"))


@app.route('/edit-post/<int:post_id>', methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = AddPostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=current_user,
        body=post.body,
        date=post.date
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        post.date = edit_form.date.data
        db.session.commit()
        return redirect(url_for("get_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route('/new-post', methods=["GET", "POST"])
@admin_only
def new_post():
    form = AddPostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=form.date.data
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("home"))
    return render_template("make-post.html", form=form, current_year=year, my_name=name)


@app.route('/contact', methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        data = request.form
        print(request.form['name'])
        print(request.form['email'])
        print(request.form['phone'])
        print(request.form['message'])
        send_email(data["name"], data["email"], data["phone"], data["message"])
        return render_template("contact.html", form_submitted=True, current_year=year, my_name=name)
    else:
        return render_template("contact.html", form_submitted=False, current_year=year, my_name=name)


def send_email(name, email, phone, message):
    email_message = f"Subject:Japan Trip: New Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage: {message}"
    with smtplib.SMTP("smtp.gmail.com") as connection:
        connection.starttls()
        connection.login(MY_EMAIL, MY_EMAIL_PASSWORD)
        connection.sendmail(MY_EMAIL, TARGET_EMAIL, email_message)


if __name__ == "__main__":
    app.run(debug=False)
