package com.epicclaimer.mobile;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String API = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US";
    private static final String STORE = "https://store.epicgames.com/en-US";
    private static final int BG = Color.rgb(13, 17, 23);
    private static final int PANEL = Color.rgb(22, 27, 34);
    private static final int TEXT = Color.rgb(230, 237, 243);
    private static final int MUTED = Color.rgb(139, 148, 158);
    private static final int BLUE = Color.rgb(47, 129, 247);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private LinearLayout cards;
    private TextView status;
    private ProgressBar progress;
    private Button refresh;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(0);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(22), dp(20), dp(12));
        root.setBackgroundColor(BG);

        TextView title = label("EPIC FREE GAMES", 23, TEXT, true);
        root.addView(title);
        TextView subtitle = label("Бесплатные игры этой недели", 14, MUTED, false);
        LinearLayout.LayoutParams subtitleLp = params(-1, -2);
        subtitleLp.topMargin = dp(5);
        root.addView(subtitle, subtitleLp);

        LinearLayout controls = new LinearLayout(this);
        controls.setGravity(Gravity.CENTER_VERTICAL);
        controls.setPadding(0, dp(15), 0, dp(13));
        status = label("Загружаю список…", 13, MUTED, false);
        controls.addView(status, new LinearLayout.LayoutParams(0, -2, 1));
        progress = new ProgressBar(this);
        progress.setIndeterminate(true);
        controls.addView(progress, params(dp(24), dp(24)));
        root.addView(controls);

        ScrollView scroll = new ScrollView(this);
        cards = new LinearLayout(this);
        cards.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(cards);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        refresh = new Button(this);
        refresh.setText("Обновить список");
        refresh.setTextColor(Color.WHITE);
        refresh.setAllCaps(false);
        refresh.setBackground(round(BLUE, 12));
        LinearLayout.LayoutParams refreshLp = params(-1, dp(50));
        refreshLp.topMargin = dp(10);
        root.addView(refresh, refreshLp);
        refresh.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) { loadGames(); }
        });

        TextView note = label("Чтобы забрать игру, войдите в Epic Games в браузере и нажмите кнопку на карточке.", 12, MUTED, false);
        note.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams noteLp = params(-1, -2);
        noteLp.topMargin = dp(8);
        root.addView(note, noteLp);
        setContentView(root);
        loadGames();
    }

    private void loadGames() {
        refresh.setEnabled(false);
        progress.setVisibility(View.VISIBLE);
        status.setText("Загружаю список…");
        executor.execute(new Runnable() {
            @Override public void run() {
                try {
                    HttpURLConnection connection = (HttpURLConnection) new URL(API).openConnection();
                    connection.setConnectTimeout(15000);
                    connection.setReadTimeout(20000);
                    connection.setRequestProperty("User-Agent", "EpicFreeGamesAndroid/1.0");
                    int code = connection.getResponseCode();
                    if (code < 200 || code >= 300) throw new IllegalStateException("HTTP " + code);
                    BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), "UTF-8"));
                    StringBuilder body = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) body.append(line);
                    reader.close();
                    connection.disconnect();
                    final JSONArray games = parseGames(new JSONObject(body.toString()));
                    runOnUiThread(new Runnable() {
                        @Override public void run() { showGames(games); }
                    });
                } catch (Exception error) {
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            progress.setVisibility(View.GONE);
                            refresh.setEnabled(true);
                            status.setText("Не удалось получить раздачи. Проверьте интернет и обновите.");
                        }
                    });
                }
            }
        });
    }

    private JSONArray parseGames(JSONObject response) throws Exception {
        JSONArray elements = response.getJSONObject("data").getJSONObject("Catalog")
                .getJSONObject("searchStore").getJSONArray("elements");
        JSONArray games = new JSONArray();
        long now = System.currentTimeMillis();
        for (int i = 0; i < elements.length(); i++) {
            JSONObject item = elements.getJSONObject(i);
            JSONObject promotions = item.optJSONObject("promotions");
            JSONArray blocks = promotions == null ? null : promotions.optJSONArray("promotionalOffers");
            boolean active = false;
            if (blocks != null) for (int b = 0; b < blocks.length(); b++) {
                JSONArray offers = blocks.optJSONObject(b).optJSONArray("promotionalOffers");
                if (offers == null) continue;
                for (int j = 0; j < offers.length(); j++) {
                    JSONObject offer = offers.getJSONObject(j);
                    JSONObject discount = offer.optJSONObject("discountSetting");
                    if (discount == null || discount.optInt("discountPercentage", -1) != 0) continue;
                    long start = parseDate(offer.optString("startDate"));
                    long end = parseDate(offer.optString("endDate"));
                    if (start <= now && now <= end) active = true;
                }
            }
            if (!active) continue;
            String slug = findSlug(item);
            if (slug.isEmpty()) continue;
            String kind = "BUNDLE".equals(item.optString("offerType")) ? "bundles" : "p";
            JSONObject game = new JSONObject();
            game.put("title", item.optString("title", "Игра"));
            game.put("url", STORE + "/" + kind + "/" + slug);
            games.put(game);
        }
        return games;
    }

    private long parseDate(String value) {
        try {
            SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
            format.setTimeZone(TimeZone.getTimeZone("UTC"));
            return format.parse(value).getTime();
        } catch (Exception first) {
            try {
                SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
                format.setTimeZone(TimeZone.getTimeZone("UTC"));
                return format.parse(value).getTime();
            } catch (Exception ignored) { return 0; }
        }
    }

    private String findSlug(JSONObject item) {
        String slug = nestedSlug(item.optJSONObject("catalogNs"), "mappings");
        if (!slug.isEmpty()) return firstPathPart(slug);
        JSONArray mappings = item.optJSONArray("offerMappings");
        if (mappings != null) for (int i = 0; i < mappings.length(); i++) {
            slug = mappings.optJSONObject(i).optString("pageSlug", "");
            if (!slug.isEmpty()) return firstPathPart(slug);
        }
        slug = item.optString("productSlug", item.optString("urlSlug", ""));
        return firstPathPart(slug);
    }

    private String nestedSlug(JSONObject object, String key) {
        JSONArray mappings = object == null ? null : object.optJSONArray(key);
        if (mappings != null) for (int i = 0; i < mappings.length(); i++) {
            String slug = mappings.optJSONObject(i).optString("pageSlug", "");
            if (!slug.isEmpty()) return slug;
        }
        return "";
    }

    private String firstPathPart(String slug) {
        int slash = slug.indexOf('/');
        return slash < 0 ? slug : slug.substring(0, slash);
    }

    private void showGames(JSONArray games) {
        progress.setVisibility(View.GONE);
        refresh.setEnabled(true);
        cards.removeAllViews();
        if (games.length() == 0) {
            status.setText("Сейчас активных бесплатных раздач нет.");
            return;
        }
        status.setText("Активных раздач: " + games.length());
        for (int i = 0; i < games.length(); i++) {
            JSONObject game = games.optJSONObject(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(dp(16), dp(14), dp(16), dp(14));
            card.setBackground(round(PANEL, 14));
            LinearLayout.LayoutParams cardLp = params(-1, -2);
            cardLp.bottomMargin = dp(10);
            cards.addView(card, cardLp);
            card.addView(label(game.optString("title"), 17, TEXT, true));
            Button open = new Button(this);
            open.setText("Открыть в Epic Games");
            open.setTextColor(Color.WHITE);
            open.setAllCaps(false);
            open.setBackground(round(BLUE, 10));
            LinearLayout.LayoutParams openLp = params(-1, dp(44));
            openLp.topMargin = dp(12);
            card.addView(open, openLp);
            final String url = game.optString("url");
            open.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View view) {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                }
            });
        }
    }

    private TextView label(String text, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private GradientDrawable round(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        return drawable;
    }

    private LinearLayout.LayoutParams params(int width, int height) {
        return new LinearLayout.LayoutParams(width, height);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
