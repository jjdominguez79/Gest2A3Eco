import 'package:flutter/material.dart';

class ContabilizacionPage extends StatelessWidget {
  const ContabilizacionPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFD8E0E8)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Contabilizacion',
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
          ),
          SizedBox(height: 8),
          Text(
            'Placeholder para pendientes de contabilizar, lotes suenlace e integracion contable.',
          ),
        ],
      ),
    );
  }
}
