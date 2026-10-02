import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/app_update/domain/app_update_policy.dart';

void main() {
  AppUpdatePolicy policy({
    bool enabled = true,
    int latestBuild = 34,
    int minimumBuild = 1,
    String storeUrl = 'https://play.google.com/store/apps/details?id=test',
  }) => AppUpdatePolicy.fromJson({
    'platform': 'android',
    'enabled': enabled,
    'latest_version': '0.1.19',
    'latest_build': latestBuild,
    'minimum_build': minimumBuild,
    'store_url': storeUrl,
  });

  test('permanece desactivada aunque exista una version superior', () {
    expect(
      policy(enabled: false).requirementFor(33),
      AppUpdateRequirement.disabled,
    );
  });

  test('avisa de forma opcional entre la version minima y la ultima', () {
    expect(
      policy(minimumBuild: 30).requirementFor(33),
      AppUpdateRequirement.optional,
    );
  });

  test('exige actualizar por debajo de la version minima', () {
    expect(
      policy(minimumBuild: 34).requirementFor(33),
      AppUpdateRequirement.mandatory,
    );
  });

  test('no muestra avisos a una version actualizada', () {
    expect(
      policy(minimumBuild: 34).requirementFor(34),
      AppUpdateRequirement.current,
    );
  });

  test('no bloquea si falta un enlace de tienda valido', () {
    expect(
      policy(minimumBuild: 34, storeUrl: '').requirementFor(1),
      AppUpdateRequirement.disabled,
    );
  });

  test('la version minima se puede aplicar sin mantener latest_build', () {
    final updatePolicy = policy(
      latestBuild: 1,
      minimumBuild: 40,
      storeUrl: '',
    );

    expect(updatePolicy.requiresMinimumBuild(39), isTrue);
    expect(updatePolicy.requiresMinimumBuild(40), isFalse);
  });

  test('el interruptor remoto desactiva tambien la version minima', () {
    final updatePolicy = policy(enabled: false, minimumBuild: 40);

    expect(updatePolicy.requiresMinimumBuild(39), isFalse);
  });
}
