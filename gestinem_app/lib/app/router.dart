import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/presentation/auth_controller.dart';
import '../features/auth/presentation/forgot_password_screen.dart';
import '../features/auth/presentation/login_screen.dart';
import '../features/campaigns/presentation/campaigns_screen.dart';
import '../features/groups/presentation/groups_screen.dart';
import '../features/messaging/presentation/conversation_screen.dart';
import '../features/messaging/presentation/conversations_screen.dart';
import '../features/profile/presentation/profile_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final session = ref.watch(sessionProvider);
  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) {
      if (session.isLoading) {
        return {'/splash', '/auth/callback'}.contains(state.matchedLocation) ? null : '/splash';
      }
      final loggedIn = session.valueOrNull != null;
      if (!loggedIn) return state.matchedLocation == '/login' ? null : '/login';
      if (state.matchedLocation == '/login' || state.matchedLocation == '/splash') return '/';
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, _) => const _SplashScreen()),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/forgot-password', builder: (_, _) => const ForgotPasswordScreen()),
      GoRoute(path: '/auth/callback', builder: (_, _) => const _SplashScreen()),
      GoRoute(path: '/', builder: (_, _) => const ConversationsScreen()),
      GoRoute(
        path: '/conversation/:id',
        builder: (_, state) => ConversationScreen(conversationId: state.pathParameters['id']!),
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
      GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen()),
    ],
  );
});

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) => const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
}
