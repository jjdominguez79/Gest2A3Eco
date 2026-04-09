import 'package:flutter/material.dart';

import '../../../core/models/dashboard_summary_model.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key, required this.summary});

  final DashboardSummaryModel summary;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Panel de ${summary.companyName}',
            style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Text(
            'Usuario actual: ${summary.userFullName} · Rol: ${summary.userRole}',
          ),
          const SizedBox(height: 24),
          Wrap(
            spacing: 16,
            runSpacing: 16,
            children: [
              _MetricCard(
                title: 'Tareas pendientes',
                value: '${summary.pendingTasks}',
              ),
              _MetricCard(
                title: 'Documentos recientes',
                value: '${summary.recentDocuments}',
              ),
              _MetricCard(title: 'Alertas', value: '${summary.alerts}'),
            ],
          ),
          const SizedBox(height: 24),
          Container(
            width: double.infinity,
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
                  'Dashboard basico funcional',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                ),
                SizedBox(height: 8),
                Text(
                  'Fase 1 deja operativos autenticacion, multiempresa, empresa activa y shell principal.',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.title, required this.value});

  final String title;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 220,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFFD8E0E8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: Color(0xFF5D7387))),
          const SizedBox(height: 12),
          Text(
            value,
            style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
