import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import 'auth_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _clientLogin() async {
    if (!_formKey.currentState!.validate()) return;
    await ref
        .read(sessionProvider.notifier)
        .loginClient(_email.text, _password.text);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(sessionProvider);
    final error = state.hasError ? apiErrorMessage(state.error!) : null;
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Image.asset(
                      'assets/images/logo_new.png',
                      height: 72,
                      semanticLabel: 'Gestinem',
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Gestinem Chat',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Mensajería segura con tu despacho',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 28),
                    Form(
                      key: _formKey,
                      child: Column(
                        children: [
                          TextFormField(
                            key: const Key('login-email'),
                            controller: _email,
                            keyboardType: TextInputType.emailAddress,
                            decoration: const InputDecoration(
                              labelText: 'Correo electrónico',
                            ),
                            validator: (value) =>
                                value != null && value.contains('@')
                                ? null
                                : 'Introduce un correo valido',
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            key: const Key('login-password'),
                            controller: _password,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Contraseña',
                            ),
                            onFieldSubmitted: (_) => _clientLogin(),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Introduce tu contraseña'
                                : null,
                          ),
                        ],
                      ),
                    ),
                    if (error != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        error,
                        key: const Key('login-error'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    FilledButton(
                      key: const Key('client-login-button'),
                      onPressed: state.isLoading ? null : _clientLogin,
                      child: state.isLoading
                          ? const SizedBox.square(
                              dimension: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Entrar como cliente'),
                    ),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 14),
                      child: Row(
                        children: [
                          Expanded(child: Divider()),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 10),
                            child: Text('o'),
                          ),
                          Expanded(child: Divider()),
                        ],
                      ),
                    ),
                    OutlinedButton.icon(
                      key: const Key('staff-login-button'),
                      onPressed: state.isLoading
                          ? null
                          : () =>
                                ref.read(sessionProvider.notifier).loginStaff(),
                      icon: const Icon(Icons.business_center_outlined),
                      label: const Text('Personal del despacho'),
                    ),
                    const SizedBox(height: 12),
                    TextButton(
                      onPressed: () => context.go('/forgot-password'),
                      child: const Text('¿Olvidaste tu contraseña?'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
