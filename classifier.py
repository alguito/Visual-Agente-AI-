"""
classifier.py - Clasificador de anomalias basado en ML
RandomForest entrenado sobre features visuales extraidas por el pipeline
"""
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import pickle
import os


class AnomalyClassifier:
    def __init__(self, model_path=None):
        self.model = None
        self.feature_names = [
            'red_pixels_pct',
            'white_pixels_pct',
            'edge_density',
            'chaos_pct',
            'img_width',
            'img_height',
            'images_without_alt',
            'total_links',
            'forms_count',
            'error_keywords_count'
        ]
        if model_path and os.path.exists(model_path):
            self.load(model_path)
        else:
            self._train_default()

    def _generate_synthetic_data(self, n=500):
        np.random.seed(42)
        X = []
        y = []
        for _ in range(n):
            features = {}
            features['red_pixels_pct'] = np.random.uniform(0, 15)
            features['white_pixels_pct'] = np.random.uniform(5, 95)
            features['edge_density'] = np.random.uniform(1, 25)
            features['chaos_pct'] = np.random.uniform(0, 60)
            features['img_width'] = np.random.uniform(800, 1920)
            features['img_height'] = np.random.uniform(600, 1080)
            features['images_without_alt'] = np.random.randint(0, 30)
            features['total_links'] = np.random.randint(5, 200)
            features['forms_count'] = np.random.randint(0, 10)
            features['error_keywords_count'] = np.random.randint(0, 8)
            score = 0
            if features['red_pixels_pct'] > 2: score += 2
            if features['red_pixels_pct'] > 8: score += 3
            if features['white_pixels_pct'] > 80: score += 3
            if features['edge_density'] > 15: score += 2
            if features['chaos_pct'] > 30: score += 3
            if features['images_without_alt'] > 10: score += 2
            if features['error_keywords_count'] > 2: score += 3
            is_anomaly = 1 if score >= 5 else 0
            X.append([features[name] for name in self.feature_names])
            y.append(is_anomaly)
        return np.array(X), np.array(y)

    def _train_default(self):
        X, y = self._generate_synthetic_data()
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            class_weight='balanced'
        )
        self.model.fit(X, y)

    def predict(self, metrics: dict) -> dict:
        if self.model is None:
            return {'is_anomaly': False, 'confidence': 0.0, 'severity': 'unknown'}
        feature_vector = []
        for name in self.feature_names:
            feature_vector.append(metrics.get(name, 0))
        X = np.array([feature_vector])
        probas = self.model.predict_proba(X)[0]
        prediction = self.model.predict(X)[0]
        confidence = max(probas)
        is_anomaly = bool(prediction == 1)
        if not is_anomaly:
            severity = 'low'
        elif confidence >= 0.8:
            severity = 'high'
        elif confidence >= 0.6:
            severity = 'medium'
        else:
            severity = 'low'
        return {
            'is_anomaly': is_anomaly,
            'confidence': round(float(confidence), 4),
            'severity': severity,
            'model': 'RandomForest (100 trees)'
        }

    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump(self.model, f)

    def load(self, path):
        with open(path, 'rb') as f:
            self.model = pickle.load(f)
