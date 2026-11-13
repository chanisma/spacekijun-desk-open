package kr.hs.kijun.classroom

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import kotlin.math.abs

/**
 * 다른 앱(PowerPoint·PDF 보기 등)을 열었을 때 화면 오른쪽에 떠 있는 «수업 화면» 단추.
 * «다른 앱 위에 표시»를 허용한 기기에서만 뜬다(기기 설정에서 허용). 위아래로 끌어 옮길 수 있다.
 */
object Bubble {
    private var view: View? = null

    @SuppressLint("ClickableViewAccessibility")
    fun show(context: Context) {
        val app = context.applicationContext
        if (view != null || !Settings.canDrawOverlays(app)) return
        val dp = { v: Float -> TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, app.resources.displayMetrics).toInt() }
        val label = TextView(app).apply {
            text = "◀  수업 화면"
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 17f
            setPadding(dp(18f), dp(14f), dp(16f), dp(14f))
            background = GradientDrawable().apply {
                setColor(0xEE4F46E5.toInt())
                cornerRadii = floatArrayOf(dp(28f).toFloat(), dp(28f).toFloat(), 0f, 0f, 0f, 0f, dp(28f).toFloat(), dp(28f).toFloat())
            }
            elevation = dp(6f).toFloat()
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.END or Gravity.CENTER_VERTICAL
            y = 0
        }
        val wm = app.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        var downY = 0f
        var startY = 0
        var moved = false
        label.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> { downY = event.rawY; startY = params.y; moved = false }
                MotionEvent.ACTION_MOVE -> {
                    val dy = (event.rawY - downY).toInt()
                    if (abs(dy) > dp(8f)) moved = true
                    if (moved) { params.y = startY + dy; runCatching { wm.updateViewLayout(label, params) } }
                }
                MotionEvent.ACTION_UP -> if (!moved) {
                    app.startActivity(Intent(app, MainActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
                }
            }
            true
        }
        runCatching { wm.addView(label, params) }.onSuccess { view = label }
    }

    fun hide(context: Context) {
        val current = view ?: return
        view = null
        val wm = context.applicationContext.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        runCatching { wm.removeView(current) }
    }
}
