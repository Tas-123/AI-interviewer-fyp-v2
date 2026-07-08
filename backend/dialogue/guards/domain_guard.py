"""Domain relevance guard — blocks wrong-topic answers before evaluation."""

from __future__ import annotations

from dialogue.guards.echo_guard import short_repeat_question
from dialogue.guards.types import GuardContext, GuardResult


def is_answer_relevant_to_question(transcript: str, last_question: str) -> bool:
    """
    Stricter domain relevance check.

    Weak but relevant answers pass; wrong-topic answers are redirected.
    """
    answer = (transcript or "").lower().strip()
    question = (last_question or "").lower().strip()

    if not answer or not question:
        return True

    if len(answer.split()) < 5:
        return True

    def has_any(items: list[str]) -> bool:
        return any(x in answer for x in items)

    def q_has_any(items: list[str]) -> bool:
        return any(x in question for x in items)

    if q_has_any([
        "python", "code stays clean", "reusable", "easy to debug",
        "structure a small machine learning project",
    ]):
        required = [
            "module", "modules", "folder", "folders", "file", "files",
            "function", "functions", "class", "classes", "package",
            "config", "configuration", "logging", "logger", "test", "tests",
            "debug", "reuse", "reusable", "structure", "separate",
            "data loading", "preprocessing", "training", "evaluation",
        ]
        wrong_only_metric = [
            "accuracy", "precision", "recall", "f1", "confusion matrix",
            "roc", "auc", "false positive", "false negative",
        ]
        if has_any(required):
            return True
        if has_any(wrong_only_metric):
            return False
        return False

    if q_has_any(["overfitting", "training accuracy", "validation performance", "reduce it"]):
        strong_required = [
            "overfitting", "validation", "validation score", "validation performance",
            "regularization", "cross validation", "cross-validation", "early stopping",
            "dropout", "reduce complexity", "simpler model", "more data", "hyperparameter",
            "max depth", "pruning", "bias", "variance", "train validation gap",
            "training and validation", "training score and validation",
            "training is high", "validation is low",
        ]
        python_structure_only = [
            "module", "modules", "folder", "folders", "configuration",
            "separate scripts", "clean code", "reusable", "debugging and reusing",
            "data loading", "project structure", "structuring into modules",
            "scripts for training", "scripts for testing",
        ]
        if has_any(python_structure_only) and not has_any(strong_required):
            return False
        if has_any(strong_required):
            return True
        return False

    if q_has_any([
        "missing values", "categorical features", "scaling", "before training",
        "preprocessing", "preprocess", "imputation", "impute", "median", "mean",
        "categorical", "encoding", "one-hot", "one hot", "one high", "won hot",
        "standard scaling", "min-max", "numeric features", "preprocessing steps",
    ]):
        required = [
            "missing", "impute", "imputation", "mean", "median", "mode",
            "categorical", "encoding", "one hot", "one-hot", "one high", "won hot",
            "label encoding", "scaling", "standard scaler", "standardscaler",
            "standard scale", "normalize", "normalization", "outlier",
            "feature", "features", "min-max",
        ]
        api_deploy_only = [
            "fastapi", "api", "endpoint", "request", "response",
            "json", "deployment", "deploy", "docker", "latency",
        ]
        if has_any(required):
            return True
        if has_any(api_deploy_only):
            return False
        return False

    if q_has_any(["accuracy", "precision", "recall", "f1", "confusion matrix", "evaluation metrics"]):
        required = [
            "accuracy", "precision", "recall", "f1", "f1-score",
            "confusion matrix", "roc", "auc", "false positive",
            "false negative", "metric", "imbalanced", "classification report",
        ]
        if has_any(required):
            return True
        return False

    if q_has_any(["speech", "nlp", "text", "preprocessing steps", "sending text to the model"]):
        required = [
            "text", "nlp", "speech", "audio", "transcript", "token",
            "tokenization", "embedding", "lowercase", "punctuation",
            "stop words", "lemmatize", "stemming", "clean", "noise",
        ]
        if has_any(required):
            return True
        return False

    if q_has_any(["api", "request", "response", "error-handling", "error handling", "expose a trained"]):
        required = [
            "api", "endpoint", "fastapi", "flask", "request", "response",
            "json", "input validation", "validation", "error handling",
            "exception", "status code", "route", "prediction",
        ]
        if has_any(required):
            return True
        return False

    if q_has_any(["deploy", "deployment", "latency", "monitor", "performance after deployment"]):
        required = [
            "deploy", "deployment", "docker", "container", "server",
            "cloud", "latency", "monitor", "logs", "logging",
            "error", "metrics", "performance", "production",
            "prometheus", "grafana", "ci/cd", "pipeline",
        ]
        if has_any(required):
            return True
        return False

    if q_has_any(["debug", "poor results", "data, preprocessing, model, or evaluation"]):
        required = [
            "debug", "data", "preprocessing", "model", "evaluation",
            "metrics", "logs", "distribution", "missing", "bias",
            "training", "validation", "pipeline",
        ]
        if has_any(required):
            return True
        return False

    if q_has_any(["introduce yourself", "project", "worked on", "showcases your ai", "machine learning skills"]):
        required = [
            "project", "built", "worked", "model", "dataset", "classification",
            "prediction", "detection", "random forest", "xgboost",
            "machine learning", "ai", "trained", "evaluated",
        ]
        if has_any(required):
            return True
        return False

    return True


def domain_relevance_redirect_response(last_question: str) -> str:
    """Redirect candidate back to the same question without scoring."""
    core_q = short_repeat_question(last_question)
    return f"Let's come back to this. {core_q}"


class DomainGuard:
    """Guard that redirects off-domain answer attempts."""

    name = "domain"

    def check(self, ctx: GuardContext) -> GuardResult:
        if is_answer_relevant_to_question(ctx.transcript, ctx.last_question):
            return GuardResult(triggered=False)

        return GuardResult(
            triggered=True,
            decision_type="DOMAIN_RELEVANCE_REDIRECT",
            response_text=domain_relevance_redirect_response(ctx.last_question),
            should_evaluate=False,
            metadata={
                "guard": self.name,
                "question": ctx.last_question,
            },
        )
