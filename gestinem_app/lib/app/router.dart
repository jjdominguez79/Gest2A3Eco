import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/presentation/auth_controller.dart';
import '../features/platform/features_provider.dart';
import '../features/auth/presentation/accept_invite_screen.dart';
import '../features/auth/presentation/forgot_password_screen.dart';
import '../features/auth/presentation/login_screen.dart';
import '../features/auth/presentation/reset_password_screen.dart';
import '../features/campaigns/presentation/campaigns_screen.dart';
import '../features/empleados/presentation/empleados_screen.dart';
import '../features/groups/presentation/groups_screen.dart';
import '../features/messaging/presentation/conversation_screen.dart';
import '../features/messaging/presentation/conversations_screen.dart';
import '../features/messaging/presentation/client_detail_screen.dart';
import '../features/messaging/presentation/clients_screen.dart';
import '../features/messaging/presentation/invite_client_screen.dart';
import '../features/invoicing/presentation/customer_form_screen.dart';
import '../features/invoicing/presentation/customer_list_screen.dart';
import '../features/invoicing/presentation/invoice_detail_screen.dart';
import '../features/invoicing/presentation/invoice_form_screen.dart';
import '../features/invoicing/presentation/invoicing_screen.dart';
import '../features/invoicing/presentation/issue_confirmation_screen.dart';
import '../features/profile/presentation/about_screen.dart';
import '../features/profile/presentation/profile_screen.dart';
import '../features/company_profile/presentation/company_profile_screen.dart';
import '../features/documents/presentation/documents_screen.dart';
import '../features/documents/presentation/document_detail_screen.dart';
import '../features/documents/presentation/document_preview_screen.dart';
import '../core/deep_links/deep_link_controller.dart';

class _RouterRefreshNotifier extends ChangeNotifier {
  void refresh() => notifyListeners();
}

bool _isProtectedClientRoute(String location) {
  final uri = Uri.tryParse(location);
  if (uri == null || uri.hasScheme || uri.host.isNotEmpty) return false;
  final path = uri.path;
  return path == '/documents' ||
      path.startsWith('/documents/') ||
      path == '/invoicing' ||
      path.startsWith('/invoicing/');
}

final routerProvider = Provider<GoRouter>((ref) {
  final session = ref.watch(sessionProvider);
  final deepLinkRoute = routeForDeepLink(ref.watch(deepLinkProvider));
  final refreshNotifier = _RouterRefreshNotifier();
  ref.onDispose(refreshNotifier.dispose);
  ref.listen<AsyncValue<PlatformFeatures>>(
    platformFeaturesProvider,
    (previous, next) => refreshNotifier.refresh(),
  );

  return GoRouter(
    refreshListenable: refreshNotifier,
    redirect: (context, state) {
      final featuresAsync = ref.read(platformFeaturesProvider);
      final loggedIn = session.valueOrNull != null;
      if (!loggedIn &&
          deepLinkRoute != null &&
          state.uri.toString() != deepLinkRoute) {
        return deepLinkRoute;
      }
      if (session.isLoading) {
        if (deepLinkRoute != null) return null;
        return {'/splash', '/auth/callback'}.contains(state.matchedLocation)
            ? null
            : '/splash';
      }
      if (!loggedIn) {
        if (state.matchedLocation == '/auth/callback') {
          return session.hasError ? '/login' : null;
        }
        if (state.matchedLocation == '/login' ||
            state.matchedLocation == '/accept-invite' ||
            state.matchedLocation == '/forgot-password' ||
            state.matchedLocation.startsWith('/reset-password')) {
          return null;
        }
        return '/login';
      }
      // Resolver ruta pendiente almacenada en ?next= cuando features cargan.
      if (state.matchedLocation == '/splash' &&
          state.uri.queryParameters.containsKey('next')) {
        final next = state.uri.queryParameters['next']!;
        if (featuresAsync.isLoading) return null; // mantener splash
        if (featuresAsync.hasError) return '/';
        if (!_isProtectedClientRoute(next)) return '/';
        final features = featuresAsync.value!;
        final nextPath = Uri.parse(next).path;
        if (nextPath.startsWith('/documents') && !features.documents) {
          return '/';
        }
        if (nextPath.startsWith('/invoicing') && !features.invoicing) {
          return '/';
        }
        return next;
      }

      if (state.matchedLocation == '/login' ||
          state.matchedLocation == '/splash' ||
          state.matchedLocation == '/accept-invite' ||
          state.matchedLocation == '/reset-password') {
        return '/';
      }
      final profile = session.valueOrNull?.profile;
      if (state.matchedLocation == '/groups' && profile?.isAdmin != true) {
        return '/';
      }

      // Proteger rutas de documentos e invoicing con observacion reactiva.
      if (state.matchedLocation.startsWith('/documents') ||
          state.matchedLocation.startsWith('/invoicing')) {
        // Mientras cargan: mostrar splash preservando la ruta destino.
        if (featuresAsync.isLoading) {
          final encoded = Uri.encodeComponent(state.uri.toString());
          return '/splash?next=$encoded';
        }
        // Si error: redirigir a inicio (conservador).
        if (featuresAsync.hasError) return '/';

        final features = featuresAsync.value!;
        if (state.matchedLocation.startsWith('/documents') &&
            !features.documents) {
          return '/';
        }
        if (state.matchedLocation.startsWith('/invoicing') &&
            !features.invoicing) {
          return '/';
        }
      }
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, _) => const _SplashScreen()),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(
        path: '/accept-invite',
        builder: (_, state) =>
            AcceptInviteScreen(token: state.uri.queryParameters['token'] ?? ''),
      ),
      GoRoute(
        path: '/forgot-password',
        builder: (_, _) => const ForgotPasswordScreen(),
      ),
      GoRoute(
        path: '/reset-password',
        builder: (_, state) => ResetPasswordScreen(
          token: state.uri.queryParameters['token'] ?? '',
        ),
      ),
      GoRoute(
        path: '/auth/callback',
        builder: (_, state) => _StaffAuthCallbackScreen(
          code: state.uri.queryParameters['code'] ?? '',
        ),
      ),
      GoRoute(path: '/', builder: (_, _) => const ConversationsScreen()),
      GoRoute(
        path: '/conversation/:id',
        builder: (_, state) =>
            ConversationScreen(conversationId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/internal/:id',
        builder: (_, state) => ConversationScreen(
          conversationId: state.pathParameters['id']!,
          internal: true,
        ),
      ),
      GoRoute(path: '/groups', builder: (_, _) => const GroupsScreen()),
      GoRoute(path: '/campaigns', builder: (_, _) => const CampaignsScreen()),
      GoRoute(path: '/employees', builder: (_, _) => const EmpleadosScreen()),
      GoRoute(path: '/clients', builder: (_, _) => const ClientsScreen()),
      GoRoute(
        path: '/clients/:companyCode',
        builder: (_, state) => ClientDetailScreen(
          companyCode: state.pathParameters['companyCode']!,
        ),
      ),
      GoRoute(
        path: '/invite-client',
        builder: (_, state) => InviteClientScreen(
          companyCode: state.uri.queryParameters['company'] ?? '',
        ),
      ),
      GoRoute(
        path: '/company-profile',
        builder: (_, _) => const CompanyProfileScreen(),
      ),
      GoRoute(path: '/documents', builder: (_, _) => const DocumentsScreen()),
      GoRoute(
        path: '/documents/folder/:folder',
        builder: (_, state) =>
            DocumentsScreen(folderKey: state.pathParameters['folder']),
      ),
      GoRoute(
        path: '/documents/:id/preview',
        builder: (_, state) =>
            DocumentPreviewScreen(documentId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/documents/:id',
        builder: (_, state) =>
            DocumentDetailScreen(documentId: state.pathParameters['id']!),
      ),
      GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen()),
      GoRoute(path: '/about', builder: (_, _) => const AboutScreen()),
      // Invoicing
      GoRoute(path: '/invoicing', builder: (_, _) => const InvoicingScreen()),
      GoRoute(
        path: '/invoicing/drafts/new',
        builder: (_, _) => const InvoiceFormScreen(),
      ),
      GoRoute(
        path: '/invoicing/drafts/:id',
        builder: (_, state) =>
            InvoiceFormScreen(draftId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/invoicing/drafts/:id/issue',
        builder: (_, state) =>
            IssueConfirmationScreen(draftId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/invoicing/invoices/:id',
        builder: (_, state) =>
            InvoiceDetailScreen(invoiceId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/invoicing/customers',
        builder: (_, _) => const CustomerListScreen(),
      ),
      GoRoute(
        path: '/invoicing/customers/new',
        builder: (_, _) => const CustomerFormScreen(),
      ),
    ],
  );
});

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}

class _StaffAuthCallbackScreen extends ConsumerStatefulWidget {
  const _StaffAuthCallbackScreen({required this.code});

  final String code;

  @override
  ConsumerState<_StaffAuthCallbackScreen> createState() =>
      _StaffAuthCallbackScreenState();
}

class _StaffAuthCallbackScreenState
    extends ConsumerState<_StaffAuthCallbackScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(_completeCallback);
  }

  Future<void> _completeCallback() async {
    while (mounted && ref.read(sessionProvider).isLoading) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    if (!mounted) return;
    if (widget.code.isEmpty) {
      context.go('/login');
      return;
    }
    await ref.read(sessionProvider.notifier).completeStaffCallback(widget.code);
  }

  @override
  Widget build(BuildContext context) => const _SplashScreen();
}
