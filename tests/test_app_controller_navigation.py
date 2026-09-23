from controllers.app_controller import AppController


class _FakeWidget:
    def __init__(self, parent=None, *, managed=False):
        self.parent = parent
        self.destroyed = False
        self.packed = False
        self._managed = managed
        if parent is not None:
            parent.children.append(self)

    def destroy(self):
        self.destroyed = True
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)

    def winfo_manager(self):
        return "pack" if self._managed or self.packed else ""

    def pack(self, **_kwargs):
        self.packed = True


class _FakeContent:
    def __init__(self):
        self.children = []

    def winfo_children(self):
        return list(self.children)

    def winfo_toplevel(self):
        return self


def _controller_with_previous():
    controller = object.__new__(AppController)
    controller._content = _FakeContent()
    controller._current_frame = _FakeWidget(controller._content, managed=True)
    controller._company_shell = object()
    controller._current_codigo = "E00001"
    controller._current_ejercicio = 2026
    return controller


def test_show_conserva_pantalla_anterior_si_falla_la_nueva(monkeypatch):
    controller = _controller_with_previous()
    previous = controller._current_frame
    shown_errors = []
    monkeypatch.setattr(
        "controllers.app_controller.messagebox.showerror",
        lambda *args, **kwargs: shown_errors.append((args, kwargs)),
    )

    def failing_factory(parent):
        partial = _FakeWidget(parent)
        raise RuntimeError("fallo controlado")

    controller._show(failing_factory)

    assert controller._current_frame is previous
    assert not previous.destroyed
    assert controller._content.children == [previous]
    assert controller._current_codigo == "E00001"
    assert shown_errors


def test_show_sustituye_pantalla_solo_despues_de_construirla():
    controller = _controller_with_previous()
    previous = controller._current_frame

    def working_factory(parent):
        return _FakeWidget(parent)

    controller._show(working_factory)

    assert previous.destroyed
    assert controller._current_frame is controller._content.children[0]
    assert controller._current_frame.packed
    assert controller._company_shell is None
    assert controller._current_codigo is None
    assert controller._current_ejercicio is None
