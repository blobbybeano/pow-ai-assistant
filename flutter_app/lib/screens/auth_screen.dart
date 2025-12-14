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
  final _nameController = TextEditingController();
  bool _isSignup = false;
  bool _isSubmitting = false;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _handleSubmit() async {
    final userController = context.read<UserController>();
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _isSubmitting = true;
      _error = null;
    });
    try {
      if (_isSignup) {
        await userController.signUp(
          email: _emailController.text.trim(),
          password: _passwordController.text.trim(),
          displayName: _nameController.text.trim(),
        );
      } else {
        await userController.signIn(
          _emailController.text.trim(),
          _passwordController.text.trim(),
        );
      }
    } catch (err) {
      setState(() {
        _error = err.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
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
                      _isSignup
                          ? 'Create your account to start collaborating.'
                          : 'Sign in with your workspace email.',
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
                    if (_isSignup)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: TextFormField(
                          controller: _nameController,
                          decoration: const InputDecoration(
                            labelText: 'Full name',
                            filled: true,
                            fillColor: Color(0xFF1F2C34),
                          ),
                          style: const TextStyle(color: Color(0xFFE9EDEF)),
                          validator: (value) {
                            if (!_isSignup) return null;
                            if (value == null || value.isEmpty) return 'Name required';
                            return null;
                          },
                        ),
                      ),
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
                        if (value == null || value.length < 8) {
                          return 'Use at least 8 characters';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(
                          _error!,
                          style: const TextStyle(color: Colors.redAccent),
                        ),
                      ),
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
                              : Text(_isSignup ? 'Create account' : 'Sign in'),
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: _isSubmitting
                          ? null
                          : () => setState(() => _isSignup = !_isSignup),
                      child: Text(
                        _isSignup
                            ? 'Have an account? Sign in'
                            : 'New to PowWash? Create account',
                        style: const TextStyle(color: Color(0xFF00A884)),
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
