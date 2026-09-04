final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

String normalizeEmail(String value) => value.trim().toLowerCase();

bool isValidEmail(String value) =>
    _emailPattern.hasMatch(normalizeEmail(value));
