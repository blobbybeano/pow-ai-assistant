import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/auth_repository.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isSubmitting = false;
  bool _isSignIn = true;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _handleSubmit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isSubmitting = true);
    final authService = context.read<AuthService>();
    try {
      if (_isSignIn) {
        await authService.signInWithEmailAndPassword(
          email: _emailController.text.trim(),
          password: _passwordController.text.trim(),
        );
      } else {
        await authService.signUpWithEmailAndPassword(
          email: _emailController.text.trim(),
          password: _passwordController.text.trim(),
        );
      }
    } on FirebaseAuthException catch (err) {
      final message = _mapFirebaseError(err);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Something went wrong. Please try again.'),
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  String _mapFirebaseError(FirebaseAuthException err) {
    switch (err.code) {
      case 'email-already-in-use':
        return 'An account already exists for that email.';
      case 'wrong-password':
        return 'Incorrect email or password.';
      case 'user-not-found':
        return 'No user found for that email.';
      case 'weak-password':
        return 'Password is too weak. Please choose a stronger one.';
      default:
        return err.message ?? 'Authentication failed. Please try again.';
    }
  }

  @override
  Widget build(BuildContext context) {
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
                      _isSignIn
                          ? 'Sign in with your workspace email.'
                          : 'Create your workspace account.',
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
                              : Text(_isSignIn ? 'Sign in' : 'Create account'),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: _isSubmitting
                          ? null
                          : () => setState(() => _isSignIn = !_isSignIn),
                      child: Text(
                        _isSignIn
                            ? 'New here? Create an account'
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
