import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../auth/presentation/auth_controller.dart';
import '../domain/conversation.dart';
import '../domain/internal_task.dart';
import 'messaging_providers.dart';

Future<void> showInternalTasksSheet(
  BuildContext context,
  InternalThread thread,
) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (_) => FractionallySizedBox(
    heightFactor: 0.9,
    child: _InternalTasksSheet(thread: thread),
  ),
);

class _InternalTasksSheet extends ConsumerStatefulWidget {
  const _InternalTasksSheet({required this.thread});

  final InternalThread thread;

  @override
  ConsumerState<_InternalTasksSheet> createState() =>
      _InternalTasksSheetState();
}

class _InternalTasksSheetState extends ConsumerState<_InternalTasksSheet> {
  final Set<String> _updating = {};

  Future<void> _createTask() async {
    final profile = ref.read(sessionProvider).valueOrNull?.profile;
    if (profile == null) return;
    final people = <String, _TaskAssignee>{
      profile.id: _TaskAssignee(profile.id, profile.name),
      for (final member in widget.thread.members)
        member.id: _TaskAssignee(member.id, member.name),
    };
    if (widget.thread.counterpartId.isNotEmpty) {
      people[widget.thread.counterpartId] = _TaskAssignee(
        widget.thread.counterpartId,
        widget.thread.title,
      );
    }
    final draft = await showDialog<_TaskDraft>(
      context: context,
      builder: (_) => _CreateTaskDialog(
        people: people.values.toList(growable: false),
        directCounterpartId: widget.thread.kind == 'direct'
            ? widget.thread.counterpartId
            : '',
      ),
    );
    if (draft == null || !mounted) return;
    try {
      await ref
          .read(messagingRepositoryProvider)
          .createInternalTask(
            widget.thread.id,
            title: draft.title,
            details: draft.details,
            assignAll: draft.assignAll,
            assigneeIds: draft.assigneeIds,
          );
      ref.invalidate(internalTasksProvider(widget.thread.id));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    }
  }

  Future<void> _toggle(InternalTask task, bool completed) async {
    if (!_updating.add(task.id)) return;
    setState(() {});
    try {
      await ref
          .read(messagingRepositoryProvider)
          .setInternalTaskCompleted(task.id, completed);
      ref.invalidate(internalTasksProvider(widget.thread.id));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(apiErrorMessage(error))));
      }
    } finally {
      _updating.remove(task.id);
      if (mounted) setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final tasks = ref.watch(internalTasksProvider(widget.thread.id));
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 12, 10),
          child: Row(
            children: [
              const Icon(Icons.checklist_rounded),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Tareas del chat',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      widget.thread.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Cerrar',
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: tasks.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(apiErrorMessage(error), textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      onPressed: () => ref.invalidate(
                        internalTasksProvider(widget.thread.id),
                      ),
                      icon: const Icon(Icons.refresh),
                      label: const Text('Reintentar'),
                    ),
                  ],
                ),
              ),
            ),
            data: (items) {
              final ordered = [...items]
                ..sort((a, b) {
                  if (a.completed != b.completed) {
                    return a.completed ? 1 : -1;
                  }
                  return b.createdAt.compareTo(a.createdAt);
                });
              if (ordered.isEmpty) {
                return const Center(
                  child: Padding(
                    padding: EdgeInsets.all(28),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.task_alt, size: 54),
                        SizedBox(height: 12),
                        Text('Todavia no hay tareas en este chat.'),
                      ],
                    ),
                  ),
                );
              }
              return RefreshIndicator(
                onRefresh: () async =>
                    ref.refresh(internalTasksProvider(widget.thread.id).future),
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 92),
                  itemCount: ordered.length,
                  itemBuilder: (_, index) {
                    final task = ordered[index];
                    return _TaskCard(
                      task: task,
                      updating: _updating.contains(task.id),
                      onChanged: task.canComplete
                          ? (value) => _toggle(task, value)
                          : null,
                    );
                  },
                ),
              );
            },
          ),
        ),
        if (widget.thread.active)
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  key: const Key('create-internal-task'),
                  onPressed: _createTask,
                  icon: const Icon(Icons.add_task),
                  label: const Text('Nueva tarea'),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _TaskCard extends StatelessWidget {
  const _TaskCard({
    required this.task,
    required this.updating,
    required this.onChanged,
  });

  final InternalTask task;
  final bool updating;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (task.canComplete)
                  Checkbox(
                    key: Key('task-checkbox-${task.id}'),
                    value: task.myCompleted,
                    onChanged: updating
                        ? null
                        : (value) => onChanged?.call(value ?? false),
                  )
                else
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: Icon(
                      task.completed
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: task.completed
                          ? colorScheme.primary
                          : colorScheme.outline,
                    ),
                  ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 9),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          task.title,
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            decoration: task.completed
                                ? TextDecoration.lineThrough
                                : null,
                          ),
                        ),
                        if (task.details.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(task.details),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(
              value: task.assigneeCount == 0
                  ? 0
                  : task.completedCount / task.assigneeCount,
            ),
            const SizedBox(height: 8),
            Text(
              task.completed
                  ? 'Completada por todos'
                  : '${task.completedCount} de ${task.assigneeCount} completadas',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final assignment in task.assignments)
                  Chip(
                    visualDensity: VisualDensity.compact,
                    avatar: Icon(
                      assignment.completed
                          ? Icons.check_circle
                          : Icons.schedule,
                      size: 18,
                      color: assignment.completed
                          ? colorScheme.primary
                          : colorScheme.outline,
                    ),
                    label: Text(assignment.name),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Creada por ${task.createdByName} · ${_dateLabel(task.createdAt)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _CreateTaskDialog extends StatefulWidget {
  const _CreateTaskDialog({
    required this.people,
    required this.directCounterpartId,
  });

  final List<_TaskAssignee> people;
  final String directCounterpartId;

  @override
  State<_CreateTaskDialog> createState() => _CreateTaskDialogState();
}

class _CreateTaskDialogState extends State<_CreateTaskDialog> {
  final _title = TextEditingController();
  final _details = TextEditingController();
  final Set<String> _selected = {};
  late bool _assignAll;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _assignAll = widget.directCounterpartId.isEmpty;
    if (widget.directCounterpartId.isNotEmpty) {
      _selected.add(widget.directCounterpartId);
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _details.dispose();
    super.dispose();
  }

  void _submit() {
    final title = _title.text.trim();
    if (title.isEmpty) {
      setState(() => _error = 'Escribe el titulo de la tarea.');
      return;
    }
    if (!_assignAll && _selected.isEmpty) {
      setState(() => _error = 'Selecciona al menos un responsable.');
      return;
    }
    Navigator.of(context).pop(
      _TaskDraft(
        title: title,
        details: _details.text.trim(),
        assignAll: _assignAll,
        assigneeIds: _selected.toList(growable: false),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Nueva tarea'),
    content: SizedBox(
      width: 480,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              key: const Key('internal-task-title'),
              controller: _title,
              autofocus: true,
              maxLength: 500,
              decoration: const InputDecoration(labelText: 'Tarea'),
            ),
            TextField(
              controller: _details,
              maxLength: 5000,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'Detalles (opcional)',
              ),
            ),
            CheckboxListTile(
              key: const Key('assign-task-to-all'),
              contentPadding: EdgeInsets.zero,
              value: _assignAll,
              onChanged: (value) => setState(() {
                _assignAll = value ?? false;
                _error = '';
              }),
              title: const Text('Asignar a todos'),
              subtitle: const Text(
                'Cada persona tendra que marcar su parte como hecha.',
              ),
            ),
            if (!_assignAll) ...[
              const SizedBox(height: 8),
              const Text(
                'Responsables',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              for (final person in widget.people)
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  value: _selected.contains(person.id),
                  onChanged: (value) => setState(() {
                    if (value ?? false) {
                      _selected.add(person.id);
                    } else {
                      _selected.remove(person.id);
                    }
                    _error = '';
                  }),
                  title: Text(person.name),
                ),
            ],
            if (_error.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _error,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Cancelar'),
      ),
      FilledButton(onPressed: _submit, child: const Text('Crear tarea')),
    ],
  );
}

class _TaskAssignee {
  const _TaskAssignee(this.id, this.name);

  final String id;
  final String name;
}

class _TaskDraft {
  const _TaskDraft({
    required this.title,
    required this.details,
    required this.assignAll,
    required this.assigneeIds,
  });

  final String title;
  final String details;
  final bool assignAll;
  final List<String> assigneeIds;
}

String _dateLabel(DateTime value) {
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(value.day)}/${two(value.month)} ${two(value.hour)}:${two(value.minute)}';
}
