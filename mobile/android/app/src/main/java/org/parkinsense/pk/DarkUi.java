package org.parkinsense.pk;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class DarkUi {
    public static final int BACKGROUND = Color.rgb(9,17,28), SURFACE = Color.rgb(20,32,48), BORDER = Color.rgb(39,57,76);
    public static final int TEXT = Color.rgb(235,243,248), MUTED = Color.rgb(162,181,197), ACCENT = Color.rgb(84,217,200), ERROR = Color.rgb(255,161,151);
    private DarkUi() { }
    public static int dp(Context context, int value) { return Math.round(value * context.getResources().getDisplayMetrics().density); }
    public static GradientDrawable background(Context context, int color, int radius) {
        GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(context, radius));
        shape.setStroke(dp(context, 1), BORDER); return shape;
    }
    public static TextView text(Context context, String text, int size, int color) {
        TextView view = new TextView(context); view.setText(text); view.setTextSize(size); view.setTextColor(color);
        view.setLineSpacing(dp(context, 3), 1f); view.setPadding(0, dp(context,4), 0, dp(context,6)); return view;
    }
    public static TextView title(Context context, String text, int size) {
        TextView view = text(context, text, size, TEXT); view.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return view;
    }
    public static LinearLayout card(Context context) {
        LinearLayout box = new LinearLayout(context); box.setOrientation(LinearLayout.VERTICAL); box.setPadding(dp(context,18),dp(context,15),dp(context,18),dp(context,15));
        box.setBackground(background(context,SURFACE,18)); LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1,-2);params.setMargins(0,dp(context,6),0,dp(context,10));box.setLayoutParams(params);return box;
    }
    public static Button button(Context context, String text, boolean primary, View.OnClickListener action) {
        Button button = new Button(context); button.setText(text); button.setAllCaps(false); button.setTextSize(16); button.setTextColor(primary ? BACKGROUND : TEXT);
        button.setBackground(background(context, primary ? ACCENT : SURFACE,12)); button.setGravity(Gravity.CENTER);button.setMinimumHeight(dp(context,52));
        button.setPadding(dp(context,16),dp(context,8),dp(context,16),dp(context,8)); LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1,dp(context,54));params.setMargins(0,dp(context,5),0,dp(context,6));button.setLayoutParams(params);button.setOnClickListener(action);return button;
    }
    public static EditText input(Context context, String hint, int type) {
        EditText input = new EditText(context);input.setTextSize(16);input.setTextColor(TEXT);input.setHintTextColor(MUTED);input.setHint(hint);input.setInputType(type);
        input.setPadding(dp(context,14),dp(context,10),dp(context,14),dp(context,10));input.setBackground(background(context,BACKGROUND,10));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.setMargins(0,dp(context,4),0,dp(context,12));input.setLayoutParams(params);input.setMinimumHeight(dp(context,54));return input;
    }
}
