import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/core/api/api_client.dart';
import 'package:gestinem/features/auth/presentation/auth_controller.dart';
import 'package:gestinem/features/platform/features_provider.dart';

import 'test_helpers.dart';

void main() {
  group('PlatformFeatures.fromJson', () {
    test('parsea respuesta completa', () {
      final features = PlatformFeatures.fromJson({
        'company_profile': true,
        'documents': true,
        'invoicing': false,
      });
      expect(features.companyProfile, true);
      expect(features.documents, true);
      expect(features.invoicing, false);
    });

    test('valores por defecto si faltan claves', () {
      final features = PlatformFeatures.fromJson({});
      expect(features.companyProfile, true);
      expect(features.documents, false);
      expect(features.invoicing, false);
    });

    test('todas las funciones activas', () {
      final features = PlatformFeatures.fromJson({
        'company_profile': true,
        'documents': true,
        'invoicing': true,
      });
      expect(features.companyProfile, true);
      expect(features.documents, true);
      expect(features.invoicing, true);
    });
  });

  group('platformFeaturesProvider', () {
    test('devuelve features del backend', () async {
      final adapter = JsonAdapter({
        'company_profile': true,
        'documents': true,
        'invoicing': false,
      });
      final container = ProviderContainer(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                ..httpClientAdapter = adapter,
              tokenProvider: () => testSession.token,
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final features = await container.read(platformFeaturesProvider.future);
      expect(features.companyProfile, true);
      expect(features.documents, true);
      expect(features.invoicing, false);
      expect(adapter.lastRequest!.path, '/client/features');
    });

    test('devuelve defaults si el endpoint falla', () async {
      final adapter = JsonAdapter({'error': 'unauthorized'}, statusCode: 401);
      final container = ProviderContainer(
        overrides: [
          sessionProvider.overrideWith(
            (ref) => FakeSessionController(ref),
          ),
          apiClientProvider.overrideWithValue(
            ApiClient(
              dio: Dio(BaseOptions(baseUrl: 'https://example.test'))
                ..httpClientAdapter = adapter,
              tokenProvider: () => testSession.token,
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final features = await container.read(platformFeaturesProvider.future);
      expect(features.companyProfile, true);
      expect(features.documents, false);
      expect(features.invoicing, false);
    });
  });
}
