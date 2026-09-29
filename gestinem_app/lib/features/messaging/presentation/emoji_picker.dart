import 'package:flutter/material.dart';

const emoticonosChat = <String>[
  '\u{1F600}',
  '\u{1F603}',
  '\u{1F604}',
  '\u{1F601}',
  '\u{1F606}',
  '\u{1F605}',
  '\u{1F602}',
  '\u{1F923}',
  '\u{1F60A}',
  '\u{1F607}',
  '\u{1F642}',
  '\u{1F643}',
  '\u{1F609}',
  '\u{1F60C}',
  '\u{1F60D}',
  '\u{1F970}',
  '\u{1F618}',
  '\u{1F61C}',
  '\u{1F92A}',
  '\u{1F914}',
  '\u{1F928}',
  '\u{1F610}',
  '\u{1F611}',
  '\u{1F644}',
  '\u{1F60F}',
  '\u{1F612}',
  '\u{1F614}',
  '\u{1F61E}',
  '\u{1F622}',
  '\u{1F62D}',
  '\u{1F624}',
  '\u{1F621}',
  '\u{1F631}',
  '\u{1F633}',
  '\u{1F92F}',
  '\u{1F973}',
  '\u{1F44D}',
  '\u{1F44E}',
  '\u{1F44F}',
  '\u{1F64C}',
  '\u{1F64F}',
  '\u{1F4AA}',
  '\u{1F91D}',
  '\u{1F44C}',
  '\u{1F91E}',
  '\u{1F44B}',
  '\u{1F4A1}',
  '\u{1F389}',
  '\u{1F381}',
  '\u{1F680}',
  '\u{1F4CC}',
  '\u{1F4C5}',
  '\u{1F4DE}',
  '\u{1F4E7}',
  '\u{2705}',
  '\u{274C}',
  '\u{26A0}\u{FE0F}',
  '\u{2764}\u{FE0F}',
  '\u{1F499}',
  '\u{1F49A}',
  '\u{1F49B}',
  '\u{1F49C}',
  '\u{2B50}',
  '\u{2728}',
];

void insertarEmoji(TextEditingController controller, String emoji) {
  final text = controller.text;
  final selection = controller.selection;
  var start = selection.isValid ? selection.start : text.length;
  var end = selection.isValid ? selection.end : text.length;
  if (start < 0 || start > text.length) start = text.length;
  if (end < start || end > text.length) end = start;

  controller.value = TextEditingValue(
    text: text.replaceRange(start, end, emoji),
    selection: TextSelection.collapsed(offset: start + emoji.length),
  );
}

class BotonSelectorEmoticonos extends StatelessWidget {
  const BotonSelectorEmoticonos({
    super.key,
    required this.controller,
    required this.focusNode,
    this.enabled = true,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool enabled;

  Future<void> _open(BuildContext context) async {
    focusNode.unfocus();
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        top: false,
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520, maxHeight: 360),
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 8, 8),
                  child: Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Emoticonos',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      IconButton(
                        key: const Key('close-emoji-picker'),
                        tooltip: 'Cerrar',
                        onPressed: () => Navigator.of(sheetContext).pop(),
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: GridView.builder(
                    key: const Key('emoji-grid'),
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 16),
                    gridDelegate:
                        const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 54,
                          mainAxisSpacing: 4,
                          crossAxisSpacing: 4,
                        ),
                    itemCount: emoticonosChat.length,
                    itemBuilder: (_, index) {
                      final emoji = emoticonosChat[index];
                      return Semantics(
                        label: 'Insertar emoticono',
                        button: true,
                        child: InkWell(
                          key: Key('emoji-option-$index'),
                          borderRadius: BorderRadius.circular(8),
                          onTap: () => insertarEmoji(controller, emoji),
                          child: Center(
                            child: Text(
                              emoji,
                              style: const TextStyle(fontSize: 27),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (context.mounted) focusNode.requestFocus();
  }

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: 'Añadir emoticono',
    onPressed: enabled ? () => _open(context) : null,
    icon: const Icon(Icons.sentiment_satisfied_alt_outlined),
  );
}
