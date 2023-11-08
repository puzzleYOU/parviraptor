import os

HELPER_SETTINGS = {
    "INSTALLED_APPS": ["parviraptor", "tests"],
    "ROOT_URLCONF": "parviraptor.urls",
    "DATABASES": {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "HOST": os.environ["DB_HOST"],
            "NAME": os.environ["DB_NAME"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "USER": os.environ["DB_USER"],
            "TEST": {
                "CHARSET": "utf8",
                "COLLATION": "utf8_general_ci",
            },
        }
    },
}
