import 'package:flutter/material.dart';

class FacturacionPage extends StatelessWidget {
  const FacturacionPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _PlaceholderModule(
      title: 'Facturacion',
      description:
          'Base del modulo de facturas emitidas, estados y futura operativa de cliente.',
    );
  }
}

class _PlaceholderModule extends StatelessWidget {
  const _PlaceholderModule({required this.title, required this.description});

  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFD8E0E8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Text(description),
        ],
      ),
    );
  }
}
