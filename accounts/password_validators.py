"""
Django's password validators with messages that say how to fix the problem.
The rules themselves are Django's own.
"""
from django.contrib.auth import password_validation as pv


class MinimumLengthValidator(pv.MinimumLengthValidator):
    def get_error_message(self):
        return f"Use at least {self.min_length} characters."


class UserAttributeSimilarityValidator(pv.UserAttributeSimilarityValidator):
    def get_error_message(self):
        return "Choose a password that isn't based on your name or email."


class CommonPasswordValidator(pv.CommonPasswordValidator):
    def get_error_message(self):
        return "This password is on a list of common passwords. Choose something less guessable."


class NumericPasswordValidator(pv.NumericPasswordValidator):
    def get_error_message(self):
        return "Add letters or symbols — a password can't be only numbers."
