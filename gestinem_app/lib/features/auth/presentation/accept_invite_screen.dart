import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import 'auth_controller.dart';

class AcceptInviteScreen extends ConsumerStatefulWidget {
  const AcceptInviteScreen({super.key, required this.token});

  final String token;

  @override
  ConsumerState<AcceptInviteScreen> createState() => _AcceptInviteScreenState();
}

class _AcceptInviteScreenState extends ConsumerState<AcceptInviteScreen> {
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _obscure = true;

  @override
  void dispose() {
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    await ref
        .read(sessionProvider.notifier)
        .acceptInvite(widget.token, _password.text);
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final error = session.hasError ? apiErrorMessage(session.error!) : null;
    return Scaffold(
      appBar: AppBar(title: const Text('Activar cuenta')),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('Crea tu contrasena',
                          style: Theme.of(context).textTheme.headlineSmall),
                      const SizedBox(height: 8),
                      const Text(
                        'Esta contrasena protege el acceso a tu canal seguro con Gestinem.',
                      ),
                      const SizedBox(height: 20),
                      TextFormField(
                        key: const Key('invite-password'),
                        controller: _password,
                        obscureText: _obscure,
                        decoration: InputDecoration(
                          labelText: 'Contrasena',
                          suffixIcon: IconButton(
                            onPressed: () => setState(() => _obscure = !_obscure),
                            icon: Icon(_obscure
                                ? Icons.visibility_off
                                : Icons.visibility),
                          ),
                        ),
                        validator: (value) => (value?.length ?? 0) < 10
                            ? 'Minimo 10 caracteres'
                            : null,
                      ),
                      const SizedBox(height: 12),
                      TextFormField(
                        key: const Key('invite-confirm'),
                        controller: _confirm,
                        obscureText: _obscure,
                        decoration:
                            const InputDecoration(labelText: 'Repite la contrasena'),
                        validator: (value) => value != _password.text
                            ? 'Las contrasenas no coinciden'
                            : null,
                      ),
                      if (error != null) ...[
                        const SizedBox(height: 12),
                        Text(error,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                      ],
                      const SizedBox(height: 20),
                      FilledButton(
                        key: const Key('accept-invite-button'),
                        onPressed: session.isLoading || widget.token.isEmpty
                            ? null
                            : _submit,
                        child: session.isLoading
                            ? const SizedBox.square(
                                dimension: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('Activar y entrar'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
