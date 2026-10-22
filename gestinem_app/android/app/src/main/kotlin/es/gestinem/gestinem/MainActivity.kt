package es.gestinem.app

import android.content.Intent
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import android.provider.Settings
import android.webkit.MimeTypeMap
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

class MainActivity : FlutterActivity() {
    companion object {
        private const val CHANNEL = "es.gestinem.app/android_integration"
        private const val MESSAGE_CHANNEL_ID = "gestinem_messages"
        private const val MAX_FILE_SIZE = 50L * 1024L * 1024L
        private const val MAX_FILES = 10
        private val ALLOWED_EXTENSIONS = setOf(
            "pdf", "png", "jpg", "jpeg", "gif", "tif", "tiff", "txt",
            "xml", "csv", "xls", "xlsx", "doc", "docx", "zip",
        )
    }

    private var integrationChannel: MethodChannel? = null
    private var initialShareConsumed = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        integrationChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL,
        ).also { channel ->
            channel.setMethodCallHandler { call, result ->
                when (call.method) {
                    "getInitialShare" -> {
                        if (initialShareConsumed) {
                            result.success(null)
                        } else {
                            initialShareConsumed = true
                            result.success(readSharedContent(intent))
                        }
                    }
                    "discardShareFiles" -> {
                        val paths = call.argument<List<String>>("paths").orEmpty()
                        discardCachedFiles(paths)
                        result.success(null)
                    }
                    "openMessageSoundSettings" -> {
                        result.success(openMessageSoundSettings())
                    }
                    else -> result.notImplemented()
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        readSharedContent(intent)?.let { payload ->
            integrationChannel?.invokeMethod("sharedContent", payload)
        }
    }

    private fun readSharedContent(source: Intent?): Map<String, Any?>? {
        val action = source?.action ?: return null
        if (action != Intent.ACTION_SEND && action != Intent.ACTION_SEND_MULTIPLE) {
            return null
        }
        cleanupOldShares()
        val copiedPaths = mutableListOf<String>()
        return try {
            val uris = sharedUris(source).distinctBy(Uri::toString)
            require(uris.isNotEmpty()) { "No se ha recibido ningun archivo." }
            require(uris.size <= MAX_FILES) {
                "Puedes compartir un maximo de $MAX_FILES archivos cada vez."
            }
            val files = uris.map { uri ->
                copyToPrivateCache(uri).also { copied ->
                    copiedPaths.add(copied["path"].toString())
                }
            }
            mapOf("files" to files)
        } catch (error: Exception) {
            discardCachedFiles(copiedPaths)
            mapOf(
                "files" to emptyList<Map<String, Any>>(),
                "error" to (error.message ?: "No se pudo recibir el archivo compartido."),
            )
        }
    }

    @Suppress("DEPRECATION")
    private fun sharedUris(source: Intent): List<Uri> {
        val result = mutableListOf<Uri>()
        if (source.action == Intent.ACTION_SEND) {
            source.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)?.let(result::add)
        } else {
            source.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.let(result::addAll)
        }
        source.clipData?.let { clip ->
            for (index in 0 until clip.itemCount) {
                clip.getItemAt(index).uri?.let(result::add)
            }
        }
        return result
    }

    private fun copyToPrivateCache(uri: Uri): Map<String, Any> {
        val metadata = queryMetadata(uri)
        val extension = metadata.first.substringAfterLast('.', "").lowercase()
        require(extension in ALLOWED_EXTENSIONS) {
            "El formato .$extension no esta admitido en Gestinem."
        }
        if (metadata.second >= 0) {
            require(metadata.second <= MAX_FILE_SIZE) {
                "${metadata.first} supera el limite de 50 MB."
            }
        }
        val directory = File(cacheDir, "received_shares").apply { mkdirs() }
        val target = File(directory, "${UUID.randomUUID()}.$extension")
        var copied = 0L
        try {
            val input = requireNotNull(contentResolver.openInputStream(uri)) {
                "No se pudo abrir ${metadata.first}."
            }
            input.use { stream ->
                FileOutputStream(target).use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    while (true) {
                        val count = stream.read(buffer)
                        if (count < 0) break
                        copied += count
                        require(copied <= MAX_FILE_SIZE) {
                            "${metadata.first} supera el limite de 50 MB."
                        }
                        output.write(buffer, 0, count)
                    }
                }
            }
        } catch (error: Exception) {
            target.delete()
            throw error
        }
        return mapOf(
            "name" to metadata.first,
            "path" to target.absolutePath,
            "size" to copied,
            "mimeType" to (contentResolver.getType(uri) ?: "application/octet-stream"),
        )
    }

    private fun queryMetadata(uri: Uri): Pair<String, Long> {
        var name: String? = null
        var size = -1L
        contentResolver.query(
            uri,
            arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (nameIndex >= 0) name = cursor.getString(nameIndex)
                if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) size = cursor.getLong(sizeIndex)
            }
        }
        var resolvedName = name?.takeIf { it.isNotBlank() } ?: fallbackName(uri)
        if (!resolvedName.contains('.')) {
            val mimeExtension = MimeTypeMap.getSingleton()
                .getExtensionFromMimeType(contentResolver.getType(uri))
                ?.lowercase()
            if (mimeExtension in ALLOWED_EXTENSIONS) {
                resolvedName = "$resolvedName.$mimeExtension"
            }
        }
        val safeName = resolvedName
            .replace(Regex("[\\\\/:*?\"<>|]"), "_")
            .take(180)
        return safeName to size
    }

    private fun fallbackName(uri: Uri): String {
        val extension = MimeTypeMap.getSingleton()
            .getExtensionFromMimeType(contentResolver.getType(uri))
            ?.takeIf { it in ALLOWED_EXTENSIONS }
            ?: "dat"
        return "archivo.$extension"
    }

    private fun discardCachedFiles(paths: List<String>) {
        val directory = File(cacheDir, "received_shares").canonicalFile
        for (path in paths) {
            runCatching {
                val file = File(path).canonicalFile
                if (file.parentFile == directory) file.delete()
            }
        }
    }

    private fun cleanupOldShares() {
        val limit = System.currentTimeMillis() - 24L * 60L * 60L * 1000L
        File(cacheDir, "received_shares").listFiles()?.forEach { file ->
            if (file.isFile && file.lastModified() < limit) file.delete()
        }
    }

    private fun openMessageSoundSettings(): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                if (manager.getNotificationChannel(MESSAGE_CHANNEL_ID) == null) {
                    manager.createNotificationChannel(
                        NotificationChannel(
                            MESSAGE_CHANNEL_ID,
                            "Mensajes",
                            NotificationManager.IMPORTANCE_HIGH,
                        ).apply {
                            description = "Avisos de nuevos mensajes de Gestinem"
                        },
                    )
                }
            }
            startActivity(
                Intent(Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS).apply {
                    putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                    putExtra(Settings.EXTRA_CHANNEL_ID, MESSAGE_CHANNEL_ID)
                },
            )
            true
        } catch (_: Exception) {
            try {
                startActivity(
                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).apply {
                        putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
                    },
                )
                true
            } catch (_: Exception) {
                false
            }
        }
    }
}
