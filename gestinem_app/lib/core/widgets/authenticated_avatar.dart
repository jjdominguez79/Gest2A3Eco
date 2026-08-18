import 'package:flutter/material.dart';

class AuthenticatedAvatar extends StatelessWidget {
  const AuthenticatedAvatar({
    super.key,
    required this.baseUrl,
    required this.authToken,
    required this.imagePath,
    required this.fallbackText,
    this.radius = 20,
    this.cacheVersion = '',
  });

  final String baseUrl;
  final String authToken;
  final String imagePath;
  final String fallbackText;
  final double radius;
  final String cacheVersion;

  @override
  Widget build(BuildContext context) {
    final fallback = Center(
      child: Text(
        fallbackText,
        maxLines: 1,
        style: TextStyle(fontSize: radius * .62, fontWeight: FontWeight.w700),
      ),
    );
    if (imagePath.isEmpty) {
      return CircleAvatar(radius: radius, child: fallback);
    }
    final uri = Uri.parse('$baseUrl$imagePath').replace(
      queryParameters: {
        ...Uri.parse('$baseUrl$imagePath').queryParameters,
        if (cacheVersion.isNotEmpty) 'v': cacheVersion,
      },
    );
    return CircleAvatar(
      radius: radius,
      child: ClipOval(
        child: Image.network(
          uri.toString(),
          width: radius * 2,
          height: radius * 2,
          fit: BoxFit.cover,
          headers: {'Authorization': 'Bearer $authToken'},
          errorBuilder: (_, _, _) =>
              SizedBox.square(dimension: radius * 2, child: fallback),
        ),
      ),
    );
  }
}
