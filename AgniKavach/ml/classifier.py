import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
import joblib

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure stdout supports UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score

from ml.feature_pipeline import FeaturePipeline
from database.connection import SessionLocal
from database.models import Hotspot
from ingestion.spatial_crossref import SpatialCrossReferencer


class FireClassifier:
    """
    Multi-Modal LightGBM Classifier for Anomaly Categorization.
    Distinguishes:
      - Class 0: forest_fire (wildfires in protected/dense forests)
      - Class 1: crop_burn (agricultural stubble burning)
      - Class 2: industrial_flare (refinery/steel/power plant emission)
      - Class 3: false_alarm (low confidence thermal artifact / reflection)
    """

    CLASS_NAMES = [
        "forest_fire",
        "crop_burn",
        "industrial_flare",
        "false_alarm"
    ]

    MODEL_DIR = Path(__file__).resolve().parent / "models"
    MODEL_PATH = MODEL_DIR / "lightgbm_fire_classifier.joblib"

    def __init__(self):
        self.model = None
        self.pipeline = FeaturePipeline()
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        if self.MODEL_PATH.exists():
            self.load_model()

    def generate_training_data(self, n_samples: int = 1200) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Generate calibrated synthetic Indian fire observation records
        modeled after real NASA FIRMS VIIRS telemetry and Bhuvan land-use patterns.
        """
        np.random.seed(42)
        records = []
        labels = []

        per_class = n_samples // 4

        # 1. Forest Fires (Simlipal, Corbett, Bandipur, Western Ghats)
        for _ in range(per_class):
            b4 = np.random.normal(350, 15)
            b5 = np.random.normal(300, 8)
            frp = np.random.exponential(35) + 15
            canopy = np.random.uniform(55, 95)
            records.append({
                "bright_ti4": b4, "bright_ti5": b5, "bright_diff": b4 - b5,
                "frp": frp, "canopy_cover_pct": canopy, "vulnerability_factor": 0.9,
                "dist_fire_station_km": np.random.uniform(15, 60),
                "dist_hospital_km": np.random.uniform(20, 70),
                "in_industrial_baseline": 0,
                "confidence_score": np.random.choice([2.0, 3.0], p=[0.3, 0.7]),
                "is_night": np.random.choice([0, 1]),
                "is_forest": 1, "is_cropland": 0, "is_industrial": 0
            })
            labels.append(0)

        # 2. Crop Burns / Stubble Burning (Punjab, Haryana, Western UP)
        for _ in range(per_class):
            b4 = np.random.normal(330, 10)
            b5 = np.random.normal(296, 6)
            frp = np.random.uniform(8, 28)
            canopy = np.random.uniform(2, 15)
            records.append({
                "bright_ti4": b4, "bright_ti5": b5, "bright_diff": b4 - b5,
                "frp": frp, "canopy_cover_pct": canopy, "vulnerability_factor": 0.45,
                "dist_fire_station_km": np.random.uniform(3, 25),
                "dist_hospital_km": np.random.uniform(4, 30),
                "in_industrial_baseline": 0,
                "confidence_score": np.random.choice([2.0, 3.0], p=[0.6, 0.4]),
                "is_night": np.random.choice([0, 1], p=[0.8, 0.2]),
                "is_forest": 0, "is_cropland": 1, "is_industrial": 0
            })
            labels.append(1)

        # 3. Industrial Flares & Smokestacks (Jamnagar, Korba, Bhilai)
        for _ in range(per_class):
            b4 = np.random.normal(370, 12)
            b5 = np.random.normal(312, 7)
            frp = np.random.uniform(40, 120)
            canopy = np.random.uniform(0, 5)
            records.append({
                "bright_ti4": b4, "bright_ti5": b5, "bright_diff": b4 - b5,
                "frp": frp, "canopy_cover_pct": canopy, "vulnerability_factor": 0.25,
                "dist_fire_station_km": np.random.uniform(1, 8),
                "dist_hospital_km": np.random.uniform(3, 25),
                "in_industrial_baseline": 1,
                "confidence_score": 3.0,
                "is_night": np.random.choice([0, 1], p=[0.5, 0.5]),
                "is_forest": 0, "is_cropland": 0, "is_industrial": 1
            })
            labels.append(2)

        # 4. False Alarms & Solar Reflections (deserts, solar panels, water glare)
        for _ in range(per_class):
            b4 = np.random.normal(315, 8)
            b5 = np.random.normal(305, 7)
            frp = np.random.uniform(1, 8)
            canopy = np.random.uniform(5, 30)
            records.append({
                "bright_ti4": b4, "bright_ti5": b5, "bright_diff": b4 - b5,
                "frp": frp, "canopy_cover_pct": canopy, "vulnerability_factor": 0.3,
                "dist_fire_station_km": np.random.uniform(10, 80),
                "dist_hospital_km": np.random.uniform(10, 80),
                "in_industrial_baseline": 0,
                "confidence_score": np.random.choice([1.0, 2.0], p=[0.7, 0.3]),
                "is_night": 0, # solar reflections only happen in daytime
                "is_forest": 0, "is_cropland": 0, "is_industrial": 0
            })
            labels.append(3)

        df = pd.DataFrame(records)[FeaturePipeline.FEATURE_COLUMNS]
        return df, pd.Series(labels)

    def train(self, n_samples: int = 1200) -> Dict[str, Any]:
        """
        Train the LightGBM classifier with stratified train/test split.
        Following ML Best Practices: Split BEFORE featurization/evaluation,
        evaluate precision, recall, and F1-score across all classes.
        """
        print(f"[ML] Generating {n_samples} stratified training observations...")
        X, y = self.generate_training_data(n_samples=n_samples)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )

        print("[ML] Training LightGBM Multi-Class Classifier...")
        clf = lgb.LGBMClassifier(
            n_estimators=120,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            random_state=42,
            verbosity=-1
        )
        clf.fit(X_train, y_train)

        # Evaluation on holdout test set
        y_pred = clf.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="weighted")
        report = classification_report(y_test, y_pred, target_names=self.CLASS_NAMES, output_dict=True)

        print(f"[SUCCESS] Model Training Completed!")
        print(f"  Accuracy: {acc * 100:.2f}%")
        print(f"  Weighted F1-Score: {f1 * 100:.2f}%\n")
        print(classification_report(y_test, y_pred, target_names=self.CLASS_NAMES))

        # Save model
        joblib.dump(clf, self.MODEL_PATH)
        self.model = clf
        print(f"[SAVE] Model serialized to: {self.MODEL_PATH.name}")

        return {
            "accuracy": acc,
            "weighted_f1": f1,
            "report": report
        }

    def load_model(self):
        """Load trained LightGBM model from disk."""
        self.model = joblib.load(self.MODEL_PATH)

    def predict(self, feature_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Predict fire category for a feature dataframe.
        Returns predicted label, probability, and class distribution.
        """
        if self.model is None:
            if self.MODEL_PATH.exists():
                self.load_model()
            else:
                self.train()

        preds = self.model.predict(feature_df)
        probs = self.model.predict_proba(feature_df)

        results = []
        for pred_idx, prob_dist in zip(preds, probs):
            pred_label = self.CLASS_NAMES[pred_idx]
            conf = float(prob_dist[pred_idx])
            prob_dict = {name: round(float(p), 4) for name, p in zip(self.CLASS_NAMES, prob_dist)}
            results.append({
                "predicted_type": pred_label,
                "confidence": round(conf, 4),
                "probabilities": prob_dict
            })
        return results

    def classify_database_hotspots(self) -> pd.DataFrame:
        """
        Fetches all hotspots from PostgreSQL, enriches them spatially,
        runs LightGBM inference, and persists the predicted fire_type back to the database.
        """
        crossref = SpatialCrossReferencer()
        enriched_df = crossref.enrich_active_hotspots()
        features = self.pipeline.transform_batch(enriched_df)

        predictions = self.predict(features)
        
        db = SessionLocal()
        try:
            for row_idx, pred in enumerate(predictions):
                hotspot_id = int(enriched_df.iloc[row_idx]["hotspot_id"])
                p_type = pred["predicted_type"]
                
                db.query(Hotspot).filter(Hotspot.id == hotspot_id).update({
                    Hotspot.fire_type: p_type
                })
            db.commit()
            print(f"[DB] Updated {len(predictions)} hotspots with predicted fire types in PostgreSQL.")
        finally:
            db.close()

        # Attach predictions to enriched DataFrame for display
        enriched_df["predicted_fire_type"] = [p["predicted_type"] for p in predictions]
        enriched_df["ml_confidence"] = [p["confidence"] for p in predictions]
        return enriched_df


if __name__ == "__main__":
    classifier = FireClassifier()
    # Train model if not already trained
    if not classifier.MODEL_PATH.exists():
        classifier.train()
    
    print("\n--- Running AI Classification on Database Hotspots ---")
    results_df = classifier.classify_database_hotspots()
    
    preview_cols = [
        "hotspot_id", "land_cover_type", "frp", "in_industrial_baseline", 
        "predicted_fire_type", "ml_confidence", "nearest_fire_station"
    ]
    print(results_df[preview_cols].to_string(index=False))
