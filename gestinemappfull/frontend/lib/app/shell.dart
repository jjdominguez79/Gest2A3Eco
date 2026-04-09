import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/state/session_controller.dart';
import '../features/company_accounts/presentation/company_accounts_page.dart';
import '../features/dashboard/presentation/dashboard_page.dart';
import '../features/documents/presentation/documents_page.dart';
import '../features/third_parties/presentation/third_parties_page.dart';

enum _ShellSection { dashboard, thirdParties, companyAccounts, documents }

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  _ShellSection _section = _ShellSection.dashboard;

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionControllerProvider);
    final controller = ref.read(sessionControllerProvider.notifier);
    final apiClient = ref.read(apiClientProvider);
    final activeCompany = session.activeCompany;
    final dashboard = session.dashboard;
    final token = session.token;

    if (activeCompany == null || dashboard == null || token == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final title = switch (_section) {
      _ShellSection.dashboard => 'Dashboard',
      _ShellSection.thirdParties => 'Terceros',
      _ShellSection.companyAccounts => 'Plan contable',
      _ShellSection.documents => 'Documentacion',
    };

    return Scaffold(
      body: Row(
        children: [
          Container(
            width: 260,
            color: const Color(0xFF0B1F2A),
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'GestinemAppFull',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Empresa activa: ${activeCompany.name}',
                  style: const TextStyle(color: Color(0xFF9FB3C8)),
                ),
                const SizedBox(height: 32),
                _NavItem(
                  icon: Icons.grid_view_rounded,
                  label: 'Dashboard',
                  selected: _section == _ShellSection.dashboard,
                  onTap: () =>
                      setState(() => _section = _ShellSection.dashboard),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: Icons.people_alt_rounded,
                  label: 'Terceros',
                  selected: _section == _ShellSection.thirdParties,
                  onTap: () =>
                      setState(() => _section = _ShellSection.thirdParties),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: Icons.account_tree_rounded,
                  label: 'Plan contable',
                  selected: _section == _ShellSection.companyAccounts,
                  onTap: () =>
                      setState(() => _section = _ShellSection.companyAccounts),
                ),
                const SizedBox(height: 8),
                _NavItem(
                  icon: Icons.folder_copy_rounded,
                  label: 'Documentacion',
                  selected: _section == _ShellSection.documents,
                  onTap: () =>
                      setState(() => _section = _ShellSection.documents),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: controller.backToCompanySelector,
                  icon: const Icon(Icons.business_rounded),
                  label: const Text('Cambiar empresa'),
                ),
                const Spacer(),
                TextButton(
                  onPressed: controller.logout,
                  child: const Text('Cerrar sesion'),
                ),
              ],
            ),
          ),
          Expanded(
            child: Column(
              children: [
                Container(
                  height: 80,
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    border: Border(
                      bottom: BorderSide(color: Color(0xFFD8E0E8)),
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          title,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE8F3F2),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          activeCompany.name,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: switch (_section) {
                      _ShellSection.dashboard => DashboardPage(
                        summary: dashboard,
                      ),
                      _ShellSection.thirdParties => ThirdPartiesPage(
                        apiClient: apiClient,
                        token: token,
                      ),
                      _ShellSection.companyAccounts => CompanyAccountsPage(
                        apiClient: apiClient,
                        token: token,
                        companyId: activeCompany.id,
                        companyName: activeCompany.name,
                      ),
                      _ShellSection.documents => DocumentsPage(
                        apiClient: apiClient,
                        token: token,
                        companyId: activeCompany.id,
                        companyName: activeCompany.name,
                      ),
                    },
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF12384A) : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        child: Row(
          children: [
            Icon(icon, color: Colors.white),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontSize: 15),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
