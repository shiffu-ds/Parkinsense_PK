# Model assets

Official small landmark models are downloaded explicitly with `scripts/download_landmark_models.py` into `landmarks`. The script records their source URLs, sizes and SHA-256 checksums in an ignored manifest. These are generic landmark extractors, not Parkinson diagnosis or functional prediction models.

Trained experimental artifacts belong in ignored `artifacts`; private models belong in ignored `private`. No real clinical training data or validated prediction weights were supplied. Never download/load arbitrary joblib artifacts: deserialization can execute code.
