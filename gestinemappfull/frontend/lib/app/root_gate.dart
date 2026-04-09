import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/state/session_controller.dart';
import '../core/state/session_state.dart';
import '../features/auth/presentation/login_page.dart';
import '../features/company_selector/presentation/company_selector_page.dart';
import 'shell.dart';

class RootGate extends ConsumerWidget {
  const RootGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionControllerProvider);

    switch (session.stage) {
      case SessionStage.unauthenticated:
        return const LoginPage();
      case SessionStage.selectingCompany:
        return const CompanySelectorPage();
      case SessionStage.ready:
        return const AppShell();
    }
  }
}
