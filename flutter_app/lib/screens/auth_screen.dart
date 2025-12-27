import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/user_controller.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _displayNameController = TextEditingController();
  bool _isLogin = true;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _displayNameController.dispose();
    super.dispose();
  }

  Future<void> _handleSubmit() async {
    if (!_formKey.currentState!.validate()) return;
    final userController = context.read<UserController>();
    setState(() => _isSubmitting = true);
    try {
      final email = _emailController.text.trim();
      final password = _passwordController.text.trim();
      final displayName = _displayNameController.text.trim();
      if (_isLogin) {
        await userController.signIn(email, password);
      } else {
        await userController.signUp(
          email: email,
          password: password,
          displayName: displayName.isEmpty ? _deriveNameFromEmail(email) : displayName,
        );
      }
    } on FirebaseAuthException catch (err) {
      _showError(err);
    } catch (err) {
      _showMessage(err.toString());
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  String _deriveNameFromEmail(String email) {
    final localPart = email.split('@').first;
    if (localPart.isEmpty) return 'Workspace user';
    final cleaned = localPart.replaceAll(RegExp(r'[._]+'), ' ').trim();
    if (cleaned.isEmpty) return 'Workspace user';
    final words = cleaned.split(RegExp(r'\s+')).where((word) => word.isNotEmpty);
    return words.map((word) => word[0].toUpperCase() + word.substring(1)).join(' ');
  }

  void _showError(FirebaseAuthException err) {
    _showMessage(
      switch (err.code) {
        'email-already-in-use' => 'An account already exists for that email.',
        'wrong-password' => 'Incorrect password. Please try again.',
        'user-not-found' => 'No account found for that email.',
        'weak-password' => 'Password should be at least 6 characters.',
        _ => err.message ?? 'Unable to process your request. Please try again.',
      },
    );
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  void _toggleMode() {
    setState(() {
      _isLogin = !_isLogin;
    });
  }

  @override
  Widget build(BuildContext context) {
    final title = _isLogin ? 'Sign in' : 'Create account';
    final subtitle = _isLogin
        ? 'Sign in with your workspace email.'
        : 'Create your PowWash workspace account.';

    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Card(
            color: const Color(0xFF111B21),
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 32),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      'PowWash Workspace',
                      style: TextStyle(
                        color: Color(0xFFE9EDEF),
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      subtitle,
                      style: const TextStyle(color: Color(0xFF8696A0)),
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      controller: _emailController,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(
                        labelText: 'Email',
                        filled: true,
                        fillColor: Color(0xFF1F2C34),
                      ),
                      style: const TextStyle(color: Color(0xFFE9EDEF)),
                      validator: (value) {
                        if (value == null || value.isEmpty) return 'Email required';
                        if (!value.contains('@')) return 'Enter a valid email';
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                    if (!_isLogin) ...[
                      TextFormField(
                        controller: _displayNameController,
                        decoration: const InputDecoration(
                          labelText: 'Name',
                          filled: true,
                          fillColor: Color(0xFF1F2C34),
                        ),
                        style: const TextStyle(color: Color(0xFFE9EDEF)),
                        validator: (value) {
                          if (_isLogin) return null;
                          if (value != null && value.trim().isNotEmpty) {
                            return null;
                          }
                          if (_emailController.text.trim().isNotEmpty) {
                            return null;
                          }
                          return 'Enter your name';
                        },
                      ),
                      const SizedBox(height: 12),
                    ],
                    TextFormField(
                      controller: _passwordController,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: 'Password',
                        filled: true,
                        fillColor: Color(0xFF1F2C34),
                      ),
                      style: const TextStyle(color: Color(0xFFE9EDEF)),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Password required';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: _isSubmitting ? null : _handleSubmit,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: _isSubmitting
                              ? const SizedBox(
                                  height: 20,
                                  width: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : Text(title),
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: _isSubmitting ? null : _toggleMode,
                      child: Text(
                        _isLogin
                            ? 'Need an account? Create one'
                            : 'Already have an account? Sign in',
                      ),
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
