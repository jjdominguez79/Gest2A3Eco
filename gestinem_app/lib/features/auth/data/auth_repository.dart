import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/config/app_config.dart';
import '../../../core/deep_links/external_auth_handoff.dart';
import '../domain/user_profile.dart';

class AuthRepository {
  AuthRepository(this._dio, {AppLinks? appLinks})
    : _appLinks = appLinks ?? AppLinks();

  final Dio _dio;
  final AppLinks _appLinks;

  Future<AuthSession> loginClient(String email, String password) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/auth/login',
      data: {'email': email.trim(), 'password': password},
    );
    final data = response.data!;
    return AuthSession(
      token: data['token'] as String,
      profile: UserProfile.fromJson(
        data['client'] as Map<String, dynamic>,
        UserType.client,
      ),
    );
  }

  Future<AuthSession> acceptInvite(String token, String password) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/auth/accept-invite',
      data: {'token': token, 'password': password},
    );
    final data = response.data!;
    return AuthSession(
      token: data['token'] as String,
      profile: UserProfile.fromJson(
        data['client'] as Map<String, dynamic>,
        UserType.client,
      ),
    );
  }

  Future<AuthSession> loginStaff() async {
    if (kIsWeb) {
      const configuredRedirect = String.fromEnvironment(
        'APP_AUTH_REDIRECT_URI',
      );
      final redirect = configuredRedirect.isNotEmpty
          ? configuredRedirect
          : Uri.base.replace(path: '/auth/callback', query: '').toString();
      final loginUrl = Uri.parse(
        '${appConfig.apiBaseUrl}/staff-auth/login',
      ).replace(queryParameters: {'app': 'true', 'web_redirect': redirect});
      if (!await launchUrl(loginUrl, webOnlyWindowName: '_self')) {
        throw StateError('No se pudo abrir el acceso de Microsoft.');
      }
      return Completer<AuthSession>().future;
    }
    final callback = _appLinks.uriLinkStream.firstWhere(
      (uri) => uri.scheme == 'es.gestinem.app' && uri.host == 'auth',
    );
    final loginUrl = Uri.parse(
      '${appConfig.apiBaseUrl}/staff-auth/login?app=true',
    );
    if (!await launchUrl(loginUrl, mode: LaunchMode.externalApplication)) {
      throw StateError('No se pudo abrir el acceso de Microsoft.');
    }
    await finishExternalAuthHandoff();
    final uri = await callback.timeout(const Duration(minutes: 5));
    final code = uri.queryParameters['code'];
    if (code == null || code.isEmpty) {
      throw StateError('Microsoft no devolvió un código de acceso.');
    }
    return exchangeStaffCode(code);
  }

  Future<AuthSession> exchangeStaffCode(String code) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/staff-auth/mobile/exchange',
      data: {'code': code},
    );
    final data = response.data!;
    return AuthSession(
      token: data['token'] as String,
      profile: UserProfile.fromJson(
        data['staff'] as Map<String, dynamic>,
        UserType.staff,
      ),
    );
  }

  Future<AuthSession?> exchangeInitialCode() async {
    final initial = await _appLinks.getInitialLink();
    final code =
        initial?.queryParameters['code'] ?? Uri.base.queryParameters['code'];
    if (code == null || code.isEmpty) return null;
    return exchangeStaffCode(code);
  }

  Future<UserProfile> currentProfile(AuthSession session) async {
    if (session.profile.type == UserType.client) {
      final response = await _dio.get<List<dynamic>>('/client/conversations');
      if (response.statusCode != 200) throw StateError('Sesión no válida');
      return session.profile;
    }
    final response = await _dio.get<Map<String, dynamic>>('/staff/me');
    return UserProfile.fromJson(response.data!, UserType.staff);
  }

  Future<void> logout(UserType type) async {
    final path = type == UserType.staff ? '/staff-auth/logout' : '/auth/logout';
    await _dio.post<void>(path);
  }
}
