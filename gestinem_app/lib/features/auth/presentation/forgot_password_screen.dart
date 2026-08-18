import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import 'auth_controller.dart';

class ForgotPasswordScreen extends ConsumerStatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  ConsumerState<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends ConsumerState<ForgotPasswordScreen> {
  final _email = TextEditingController();
  bool _loading = false;
  bool _sent = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _email.text.trim();
    if (email.isEmpty || !email.contains('@')) {
      setState(() => _error = 'Introduce un correo valido');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      await api.dio.post<void>(
        '/auth/forgot-password',
        data: {'email': email},
      );
      if (mounted) setState(() => _sent = true);
    } catch (e) {
      if (mounted) setState(() => _error = apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Recuperar contraseña')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 440),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: _sent
                ? const _SentCard()
                : _FormCard(
                    email: _email,
                    loading: _loading,
                    error: _error,
                    onSubmit: _submit,
                  ),
          ),
        ),
      ),
    );
  }
}

class _SentCard extends StatelessWidget {
  const _SentCard();

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.mark_email_read_outlined,
                  size: 48, color: Color(0xFF004B76)),
              const SizedBox(height: 16),
              Text('Revisa tu correo',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text(
                'Si existe una cuenta con ese correo, recibirás un enlace para restablecer tu contraseña.',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      );
}

class _FormCard extends StatelessWidget {
  const _FormCard({
    required this.email,
    required this.loading,
    this.error,
    required this.onSubmit,
  });

  final TextEditingController email;
  final bool loading;
  final String? error;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '¿Olvidaste tu contraseña?',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              const Text(
                'Introduce tu correo electrónico y te enviaremos un enlace para restablecer tu contraseña.',
              ),
              const SizedBox(height: 20),
              TextField(
                controller: email,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Correo electrónico'),
              ),
              if (error != null) ...[
                const SizedBox(height: 8),
                Text(
                  error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton(
                onPressed: loading ? null : onSubmit,
                child: loading
                    ? const SizedBox.square(
                        dimension: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Enviar enlace'),
              ),
            ],
          ),
        ),
      );
}
