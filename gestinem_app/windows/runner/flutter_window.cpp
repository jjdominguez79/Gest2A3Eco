#include "flutter_window.h"

#include <algorithm>
#include <optional>
#include <string>
#include <vector>

#include <flutter/standard_method_codec.h>

#include "flutter/generated_plugin_registrant.h"

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  taskbar_button_created_message_ =
      RegisterWindowMessage(L"TaskbarButtonCreated");
  if (SUCCEEDED(CoCreateInstance(CLSID_TaskbarList, nullptr,
                                 CLSCTX_INPROC_SERVER,
                                 IID_PPV_ARGS(&taskbar_list_)))) {
    taskbar_list_->HrInit();
  }

  taskbar_badge_channel_ = std::make_unique<
      flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(),
      "es.gestinem.app/taskbar_badge",
      &flutter::StandardMethodCodec::GetInstance());
  taskbar_badge_channel_->SetMethodCallHandler(
      [this](const flutter::MethodCall<flutter::EncodableValue>& call,
             std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>>
                 result) {
        if (call.method_name() != "setBadge") {
          result->NotImplemented();
          return;
        }
        int count = 0;
        if (const auto* arguments = call.arguments()) {
          if (const auto* value32 = std::get_if<int32_t>(arguments)) {
            count = *value32;
          } else if (const auto* value64 = std::get_if<int64_t>(arguments)) {
            count = static_cast<int>(std::clamp<int64_t>(*value64, 0, 999999));
          } else {
            result->Error("invalid_argument",
                          "El contador debe ser un numero entero");
            return;
          }
        }
        SetTaskbarBadge(std::clamp(count, 0, 999999));
        result->Success();
      });

  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    this->Show();
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  if (taskbar_badge_channel_) {
    taskbar_badge_channel_->SetMethodCallHandler(nullptr);
    taskbar_badge_channel_.reset();
  }
  if (taskbar_list_) {
    taskbar_list_->SetOverlayIcon(GetHandle(), nullptr, L"");
    taskbar_list_->Release();
    taskbar_list_ = nullptr;
  }
  if (taskbar_badge_icon_) {
    DestroyIcon(taskbar_badge_icon_);
    taskbar_badge_icon_ = nullptr;
  }
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  if (message == taskbar_button_created_message_) {
    ApplyTaskbarBadge();
    return 0;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}

void FlutterWindow::SetTaskbarBadge(int count) {
  taskbar_badge_count_ = count;
  ApplyTaskbarBadge();
}

void FlutterWindow::ApplyTaskbarBadge() {
  if (!taskbar_list_ || !GetHandle()) {
    return;
  }

  if (taskbar_badge_count_ <= 0) {
    taskbar_list_->SetOverlayIcon(GetHandle(), nullptr, L"");
    if (taskbar_badge_icon_) {
      DestroyIcon(taskbar_badge_icon_);
      taskbar_badge_icon_ = nullptr;
    }
    return;
  }

  HICON next_icon = CreateTaskbarBadgeIcon(taskbar_badge_count_);
  if (!next_icon) {
    return;
  }
  const std::wstring description =
      std::to_wstring(taskbar_badge_count_) +
      (taskbar_badge_count_ == 1 ? L" mensaje pendiente"
                                 : L" mensajes pendientes");
  if (SUCCEEDED(taskbar_list_->SetOverlayIcon(
          GetHandle(), next_icon, description.c_str()))) {
    if (taskbar_badge_icon_) {
      DestroyIcon(taskbar_badge_icon_);
    }
    taskbar_badge_icon_ = next_icon;
  } else {
    DestroyIcon(next_icon);
  }
}

HICON FlutterWindow::CreateTaskbarBadgeIcon(int count) const {
  constexpr int kSize = 32;
  BITMAPV5HEADER header{};
  header.bV5Size = sizeof(header);
  header.bV5Width = kSize;
  header.bV5Height = -kSize;
  header.bV5Planes = 1;
  header.bV5BitCount = 32;
  header.bV5Compression = BI_BITFIELDS;
  header.bV5RedMask = 0x00FF0000;
  header.bV5GreenMask = 0x0000FF00;
  header.bV5BlueMask = 0x000000FF;
  header.bV5AlphaMask = 0xFF000000;

  void* raw_pixels = nullptr;
  HDC screen = GetDC(nullptr);
  HBITMAP color = CreateDIBSection(
      screen, reinterpret_cast<BITMAPINFO*>(&header), DIB_RGB_COLORS,
      &raw_pixels, nullptr, 0);
  ReleaseDC(nullptr, screen);
  if (!color || !raw_pixels) {
    if (color) DeleteObject(color);
    return nullptr;
  }

  auto* pixels = static_cast<uint32_t*>(raw_pixels);
  std::fill(pixels, pixels + (kSize * kSize), 0);

  HDC canvas = CreateCompatibleDC(nullptr);
  HGDIOBJ old_bitmap = SelectObject(canvas, color);
  HBRUSH background = CreateSolidBrush(RGB(211, 47, 47));
  HGDIOBJ old_brush = SelectObject(canvas, background);
  HGDIOBJ old_pen = SelectObject(canvas, GetStockObject(NULL_PEN));
  Ellipse(canvas, 0, 0, kSize, kSize);

  const std::wstring label = count > 99 ? L"99+" : std::to_wstring(count);
  const int font_height = label.size() == 1 ? 23 : (label.size() == 2 ? 19 : 14);
  HFONT font = CreateFontW(
      -font_height, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,
      DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
      NONANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
  HGDIOBJ old_font = SelectObject(canvas, font);
  SetBkMode(canvas, TRANSPARENT);
  SetTextColor(canvas, RGB(255, 255, 255));
  RECT bounds{0, label.size() == 1 ? -1L : 0L, kSize, kSize};
  DrawTextW(canvas, label.c_str(), -1, &bounds,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);

  // GDI no conserva el canal alfa al dibujar. Los pixeles pintados se hacen
  // opacos y el exterior negro del circulo permanece transparente.
  for (int index = 0; index < kSize * kSize; ++index) {
    if ((pixels[index] & 0x00FFFFFF) != 0) {
      pixels[index] |= 0xFF000000;
    }
  }

  SelectObject(canvas, old_font);
  SelectObject(canvas, old_pen);
  SelectObject(canvas, old_brush);
  SelectObject(canvas, old_bitmap);
  DeleteObject(font);
  DeleteObject(background);
  DeleteDC(canvas);

  std::vector<uint8_t> mask_bits((kSize * kSize) / 8, 0);
  HBITMAP mask = CreateBitmap(kSize, kSize, 1, 1, mask_bits.data());
  ICONINFO info{};
  info.fIcon = TRUE;
  info.hbmColor = color;
  info.hbmMask = mask;
  HICON icon = CreateIconIndirect(&info);
  DeleteObject(mask);
  DeleteObject(color);
  return icon;
}
