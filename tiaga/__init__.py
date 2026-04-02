import warnings

warnings.filterwarnings(
    "ignore",
    message=r".*Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater.*",
)

warnings.filterwarnings(
    "ignore",
    message=r".*Pydantic serializer warnings.*",
)
