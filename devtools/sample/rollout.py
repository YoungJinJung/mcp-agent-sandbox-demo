"""Intentionally broken replica-count check for the CI reproduction exercise.

This sample is not a complete Kubernetes Deployment readiness check.
"""


def replicas_ready(desired, available):
    return available > 0
