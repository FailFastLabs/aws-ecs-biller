from .base import *  # noqa: F401, F403

DEBUG = True
SECRET_KEY = "dev-secret-key-not-for-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "aws_cur",
        "USER": "cur_user",
        "PASSWORD": "devpassword",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
