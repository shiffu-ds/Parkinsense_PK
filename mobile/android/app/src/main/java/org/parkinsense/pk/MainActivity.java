package org.parkinsense.pk;

import android.content.Intent;
import android.graphics.Typeface;
import android.media.MediaPlayer;
import android.net.Uri;
import java.io.InputStream;
import java.io.FileOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import android.os.Bundle;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.VideoView;
import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Patient-only native UI. Recording is private until the patient explicitly uploads it. */
public final class MainActivity extends AppCompatActivity {
    private static final String[] LANGUAGES={"English","Urdu","Pashto","Mixed","Roman Urdu"};
    private static final String[] VIDEO_TASKS={"gait","turning","finger_left","finger_right","hand_open_close","sit_to_stand","reach","grasp","object_transfer"};
    private static final String[] VIDEO_NAMES={"Walking","Turning","Left finger tapping","Right finger tapping","Hand opening and closing","Sit to stand","Reaching","Grasping","Object transfer"};
    private static final String[] AUDIO_TASKS={"vowel","sentence","natural"};
    private static final String[] AUDIO_NAMES={"Sustained vowel","Read a sentence","Natural speech"};
    private static final String[] ACTIVITY_KEYS={"dressing","feeding","grooming","bathing","writing","phone_use","walking","transfers","household_activities"};
    private static final String[] ACTIVITY_NAMES={"Getting dressed","Eating","Personal grooming","Bathing","Writing","Using a phone","Walking","Getting up / transferring","Household activities"};
    private TokenStore store; private ApiClient api; private JSONObject profile;
    private LinearLayout body, root; private TextView status; private List<Button> controls=new ArrayList<>();
    private long screen; private boolean busy; private String draftId, capturedTask, capturedMime, currentPage="home";
    private final ExecutorService importExecutor=Executors.newSingleThreadExecutor();
    private File capturedFile; private MediaPlayer player; private VideoView preview;
    private final ActivityResultLauncher<String[]> picker=registerForActivityResult(new ActivityResultContracts.OpenDocument(), uri -> {
        if(uri==null){showLiveChoice();return;}importClip(uri);
    });
    private final ActivityResultLauncher<Intent> capture=registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result -> {
        if(result.getResultCode()!=RESULT_OK || result.getData()==null) { showLiveChoice(); return; }
        Intent data=result.getData();
        File file=safeClip(data.getStringExtra(LiveCheckerActivity.EXTRA_RECORDING_PATH));
        if(file==null) { showLiveChoice(); notice("The recording could not be found. Please try again.",true); return; }
        capturedFile=file; capturedMime=data.getStringExtra(LiveCheckerActivity.EXTRA_MIME_TYPE);capturedTask=data.getStringExtra(LiveCheckerActivity.EXTRA_TASK_CODE);
        if(!"video/mp4".equals(capturedMime)&&!"audio/wav".equals(capturedMime)) { discardClip();showLiveChoice();notice("This recording format is not supported.",true);return; }
        showClipReview();
    });
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        store=new TokenStore(this);api=new ApiClient(store);
        if(state!=null) {
            draftId=state.getString("draft");capturedTask=state.getString("task");capturedMime=state.getString("mime");capturedFile=safeClip(state.getString("clip"));
        }
        purgeAbandonedClips();
        getOnBackPressedDispatcher().addCallback(this,new OnBackPressedCallback(true){@Override public void handleOnBackPressed(){
            if(busy){Toast.makeText(MainActivity.this,"Please wait for the current request.",Toast.LENGTH_SHORT).show();return;}
            if(capturedFile!=null){confirmDiscard(()->showDashboard());return;}
            if(store.token()!=null && !currentPage.equals("home")){showDashboard();return;}
            if(store.token()==null&&!currentPage.equals("login")){showAuth(false);return;}
            finish();
        }});
        if(store.token()==null)showAuth(false);else loadProfile();
    }
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("draft",draftId);out.putString("task",capturedTask);out.putString("mime",capturedMime);if(capturedFile!=null)out.putString("clip",capturedFile.getAbsolutePath());}
    @Override protected void onStop(){super.onStop();releasePlayback();}
    @Override protected void onDestroy(){releasePlayback();if(api!=null)api.close();importExecutor.shutdownNow();super.onDestroy();}
    private File safeClip(String path){if(path==null)return null;try{File f=new File(path).getCanonicalFile();String base=getCacheDir().getCanonicalPath()+File.separator;return f.isFile()&&f.getPath().startsWith(base)?f:null;}catch(Exception e){return null;}}
    private void purgeAbandonedClips(){File[] files=getCacheDir().listFiles();if(files==null)return;for(File file:files){if((file.getName().startsWith("ps-video-")||file.getName().startsWith("ps-audio-"))&&(capturedFile==null||!file.equals(capturedFile))&&System.currentTimeMillis()-file.lastModified()>24L*60*60*1000)file.delete();}}
    private void releasePlayback(){if(player!=null){player.release();player=null;}if(preview!=null){preview.stopPlayback();preview=null;}}
    private void page(String name,String title,String subtitle,boolean navigation){
        releasePlayback();screen++;busy=false;controls=new ArrayList<>();currentPage=name;
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(DarkUi.BACKGROUND);
        root.setPadding(DarkUi.dp(this,18),0,DarkUi.dp(this,18),0);setContentView(root);
        ViewCompat.setOnApplyWindowInsetsListener(root,(view,insets)->{Insets bars=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());Insets ime=insets.getInsets(WindowInsetsCompat.Type.ime());view.setPadding(DarkUi.dp(this,18)+bars.left,bars.top+DarkUi.dp(this,12),DarkUi.dp(this,18)+bars.right,Math.max(bars.bottom,ime.bottom)+DarkUi.dp(this,8));return insets;});
        ViewCompat.requestApplyInsets(root);
        root.addView(DarkUi.text(this,"PARKINSENSE PK",12,DarkUi.ACCENT));root.addView(DarkUi.title(this,title,28));if(!subtitle.isEmpty())root.addView(DarkUi.text(this,subtitle,14,DarkUi.MUTED));
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1f));
        body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(0,DarkUi.dp(this,10),0,DarkUi.dp(this,12));scroll.addView(body);
        status=DarkUi.text(this,"",14,DarkUi.MUTED);status.setVisibility(View.GONE);body.addView(status);
        if(navigation){LinearLayout nav=new LinearLayout(this);nav.setOrientation(LinearLayout.HORIZONTAL);nav.setGravity(Gravity.CENTER);root.addView(nav);navButton(nav,"Home",()->showDashboard());navButton(nav,"History",()->showHistory());navButton(nav,"Account",()->showAccount());}
    }
    private void navButton(LinearLayout nav,String label,Runnable action){Button button=DarkUi.button(this,label,false,v->{if(!busy)action.run();});button.setTextSize(13);button.setPadding(0,0,0,0);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,DarkUi.dp(this,48),1);p.setMargins(DarkUi.dp(this,2),DarkUi.dp(this,5),DarkUi.dp(this,2),0);nav.addView(button,p);controls.add(button);}
    private LinearLayout card(String title,String description){LinearLayout c=DarkUi.card(this);body.addView(c);if(title!=null&&!title.trim().isEmpty())c.addView(DarkUi.title(this,title,18));if(description!=null&&!description.trim().isEmpty())c.addView(DarkUi.text(this,description,14,DarkUi.MUTED));return c;}
    private Button button(LinearLayout parent,String label,boolean primary,Runnable action){Button b=DarkUi.button(this,label,primary,v->{if(!busy)action.run();});parent.addView(b);controls.add(b);if(busy)b.setEnabled(false);return b;}
    private void notice(String text,boolean error){status.setVisibility(View.VISIBLE);status.setText(text);status.setTextColor(error?DarkUi.ERROR:DarkUi.ACCENT);}
    private void working(String text){busy=true;notice(text,false);for(Button b:controls)b.setEnabled(false);}
    private void idle(){busy=false;for(Button b:controls)b.setEnabled(true);}
    private ApiClient.Callback callback(long epoch, java.util.function.Consumer<Object> done){return new ApiClient.Callback(){public void success(Object data){if(epoch!=screen)return;idle();done.accept(data);}public void failure(int code,String message){if(epoch!=screen)return;idle();if(code==401&&store.token()!=null){api.invalidate();store.clear();discardClip();draftId=null;profile=null;showAuth(false);}notice(message,true);}};}
    private void loadProfile(){page("home","Your personal space","Connecting to your patient account…",false);working("Loading account…");api.get("/profile",callback(screen,data->{profile=(JSONObject)data;if(capturedFile!=null)showClipReview();else showDashboard();}));button(body,"Change server",false,()->showServer());}
    private void showAuth(boolean register){
        page(register?"register":"login",register?"Create your account":"Welcome back",register?"A private account for your own recordings and daily check-ins.":"Sign in to see your personal history and start a new recording.",false);
        LinearLayout c=card(register?"Register":"Login",null);
        EditText name=register?DarkUi.input(this,"Full name",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PERSON_NAME):null;if(name!=null)c.addView(name);
        EditText email=DarkUi.input(this,"Email",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);email.setSingleLine(true);c.addView(email);
        EditText password=DarkUi.input(this,register?"Password (at least 12 characters)":"Password",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);password.setSingleLine(true);password.setSaveEnabled(false);c.addView(password);
        Spinner language=register?spinner(LANGUAGES):null;CheckBox consent=null;
        if(register){c.addView(DarkUi.text(this,"Preferred language",14,DarkUi.MUTED));c.addView(language);consent=new CheckBox(this);consent.setText("I agree to store my personal recordings and daily check-ins for my own monitoring.");consent.setTextColor(DarkUi.TEXT);consent.setTextSize(14);consent.setPadding(0,DarkUi.dp(this,8),0,DarkUi.dp(this,10));c.addView(consent);c.addView(DarkUi.text(this,"Live camera and microphone analysis runs on this phone. Saved recordings are sent to your configured server only after you tap Upload. Measurements do not diagnose Parkinson’s or provide treatment advice.",13,DarkUi.MUTED));}
        final CheckBox accepted=consent;
        button(c,register?"Create account":"Login",true,()->{
            String address=email.getText().toString().trim(),secret=password.getText().toString();
            if(!android.util.Patterns.EMAIL_ADDRESS.matcher(address).matches()){notice("Enter your email address.",true);return;}
            if(secret.length()<(register?12:1)||secret.length()>128){notice(register?"Use a password of 12 to 128 characters.":"Enter your password.",true);return;}
            if(register&&(name.getText().toString().trim().length()<2||!accepted.isChecked())){notice("Enter your name and accept personal monitoring consent.",true);return;}
            try{JSONObject json=new JSONObject().put("email",address).put("password",secret);if(register)json.put("full_name",name.getText().toString().trim()).put("language",language.getSelectedItem().toString()).put("consent",true);
                working(register?"Creating your account…":"Signing in…");api.post(register?"/auth/register":"/auth/login",json,callback(screen,data->{try{JSONObject value=(JSONObject)data;store.save(value.getString("access_token"));api.invalidate();profile=value.getJSONObject("user");password.setText("");showDashboard();}catch(Exception e){store.clear();notice("Secure sign-in could not be saved. Please try again.",true);}}));
            }catch(Exception e){notice("Check your account details.",true);}
        });
        button(body,register?"Already have an account? Login":"New here? Register",false,()->showAuth(!register));button(body,"Server connection",false,()->showServer());
        body.addView(DarkUi.text(this,"Connected server: "+store.server()+"\nPrivate Wi-Fi preview • patient use only",12,DarkUi.MUTED));
    }
    private Spinner spinner(String[] items){Spinner s=new Spinner(this);ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,items);adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);s.setAdapter(adapter);s.setBackground(DarkUi.background(this,DarkUi.BACKGROUND,10));s.setPadding(DarkUi.dp(this,10),0,DarkUi.dp(this,10),0);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,DarkUi.dp(this,54));p.setMargins(0,DarkUi.dp(this,3),0,DarkUi.dp(this,12));s.setLayoutParams(p);return s;}
    private void showDashboard(){
        if(store.token()==null){showAuth(false);return;}String name=profile==null?"":", "+profile.optString("full_name","");
        page("home","Hello"+name,"Keep a personal record of your movement, voice and everyday activities.",true);
        LinearLayout live=card("Live Checker","Record movement or voice and see recording quality update as you go.");button(live,"Start Live Checker",true,()->showLiveChoice());
        LinearLayout check=card("Daily check-in","Describe how your usual activities feel today. Your own notes stay with your account.");button(check,"Add activities and notes",false,()->showCheckIn());
        if(draftId!=null){LinearLayout draft=card("Recording in progress","You have an unfinished session on this phone.");button(draft,"Continue session",false,()->openSession(draftId));}
        LinearLayout history=card("Your progress","Review saved sessions and technical changes from previous recordings.");button(history,"View history",false,()->showHistory());
        body.addView(DarkUi.text(this,"ParkinSense provides technical measurements for personal monitoring. It does not diagnose a condition or replace advice from your healthcare professional.",13,DarkUi.MUTED));
    }
    private void showLiveChoice(){
        if(store.token()==null){showAuth(false);return;}
        page("live","Live Checker","Choose a task. Camera or microphone access starts only after you tap Start in the recorder.",true);
        LinearLayout v=card("Movement recording","The preview shows lighting, image detail and pixel change during recording. These are recording signals, not clinical scores.");Spinner video=spinner(VIDEO_NAMES);v.addView(video);button(v,"Open camera recorder",true,()->launchCapture("video",VIDEO_TASKS[video.getSelectedItemPosition()],VIDEO_NAMES[video.getSelectedItemPosition()]));button(v,"Use an existing MP4 video",false,()->{capturedTask=VIDEO_TASKS[video.getSelectedItemPosition()];capturedMime="video/mp4";picker.launch(new String[]{"video/mp4"});});
        LinearLayout a=card("Voice recording","Watch the live sound level, silence and clipping while a WAV recording is created on your phone.");Spinner audio=spinner(AUDIO_NAMES);a.addView(audio);button(a,"Open voice recorder",true,()->launchCapture("audio",AUDIO_TASKS[audio.getSelectedItemPosition()],AUDIO_NAMES[audio.getSelectedItemPosition()]));button(a,"Use an existing WAV recording",false,()->{capturedTask=AUDIO_TASKS[audio.getSelectedItemPosition()];capturedMime="audio/wav";picker.launch(new String[]{"audio/wav","audio/x-wav"});});
        body.addView(DarkUi.text(this,"Choose a safe space. Stop if you feel unsteady, tired or uncomfortable. Use the same setup each time for more useful comparisons.",13,DarkUi.MUTED));
    }
    private void importClip(Uri uri){
        page("import","Preparing your recording","Copying your selected file into private temporary app storage.",false);working("Loading recording…");final long epoch=screen;final String mime=capturedMime;final String task=capturedTask;
        importExecutor.execute(()->{File file=null;try{if(!"video/mp4".equals(mime)&&!"audio/wav".equals(mime))throw new IllegalArgumentException();file=File.createTempFile(mime.startsWith("video")?"ps-video-":"ps-audio-",mime.startsWith("video")?".mp4":".wav",getCacheDir());try(InputStream input=getContentResolver().openInputStream(uri);FileOutputStream output=new FileOutputStream(file)){if(input==null)throw new IllegalArgumentException();byte[] buffer=new byte[32768];int length;long total=0;while((length=input.read(buffer))!=-1){if(Thread.currentThread().isInterrupted())throw new InterruptedException();total+=length;if(total>100L*1024*1024)throw new IllegalArgumentException();output.write(buffer,0,length);}if(total==0)throw new IllegalArgumentException();}final File ready=file;runOnUiThread(()->{if(isDestroyed()||epoch!=screen){ready.delete();return;}capturedFile=ready;capturedMime=mime;capturedTask=task;showClipReview();});}catch(Exception e){if(file!=null)file.delete();runOnUiThread(()->{if(!isDestroyed()&&epoch==screen){showLiveChoice();notice("Could not read this recording. Choose an MP4 video or WAV audio file smaller than 100 MB.",true);}});}});
    }
    private void launchCapture(String mode,String task,String name){Intent intent=new Intent(this,LiveCheckerActivity.class);intent.putExtra(LiveCheckerActivity.EXTRA_MODE,mode);intent.putExtra(LiveCheckerActivity.EXTRA_TASK_CODE,task);intent.putExtra(LiveCheckerActivity.EXTRA_TASK_NAME,name);capture.launch(intent);}
    private void showClipReview(){
        page("review","Review your recording","This clip is still private on this phone. Upload sends it to your configured patient server for analysis.",false);
        LinearLayout c=card(taskName(capturedTask),String.format(Locale.ROOT,"%s • %.2f MB",capturedMime.startsWith("video")?"Movement video":"Voice recording",capturedFile.length()/1048576d));
        if(capturedMime.startsWith("video")){preview=new VideoView(this);preview.setVideoPath(capturedFile.getAbsolutePath());c.addView(preview,new LinearLayout.LayoutParams(-1,DarkUi.dp(this,210)));final VideoView clipView=preview;button(c,"Play / replay recording",false,()->{if(capturedFile==null)return;clipView.setVideoPath(capturedFile.getAbsolutePath());preview=clipView;clipView.start();});}
        else button(c,"Play voice recording",false,()->{try{releasePlayback();player=new MediaPlayer();player.setDataSource(capturedFile.getAbsolutePath());player.setOnCompletionListener(p->{p.release();if(player==p)player=null;});player.prepare();player.start();}catch(Exception e){releasePlayback();notice("Playback could not start. You can still upload or discard.",true);}});
        button(c,"Upload and analyse",true,()->uploadClip());button(body,"Discard recording",false,()->confirmDiscard(()->showLiveChoice()));
        body.addView(DarkUi.text(this,"Server: "+store.server()+"\nOnly accepted recordings are saved to your personal session. Connection failures keep this clip available for retry.",13,DarkUi.MUTED));
    }
    private void confirmDiscard(Runnable next){new AlertDialog.Builder(this).setTitle("Discard unsaved recording?").setMessage("This deletes the clip from this phone.").setNegativeButton("Keep recording",(d,w)->{}).setPositiveButton("Discard",(d,w)->{discardClip();next.run();}).show();}
    private void discardClip(){releasePlayback();if(capturedFile!=null){capturedFile.delete();capturedFile=null;}capturedTask=null;capturedMime=null;}
    private void ensureDraft(java.util.function.Consumer<String> ready){
        if(draftId!=null){ready.accept(draftId);return;}
        api.post("/sessions",new JSONObject(),callback(screen,data->{JSONObject session=(JSONObject)data;draftId=session.optString("id",null);if(draftId==null){notice("The server did not create a session.",true);return;}ready.accept(draftId);}));
    }
    private void uploadClip(){
        if(capturedFile==null)return;working("Creating your personal session…");
        ensureDraft(id->{working("Uploading and analysing your recording. Keep this screen open…");api.upload("/sessions/"+id+(capturedMime.startsWith("video")?"/video":"/audio"),capturedFile,capturedMime,capturedTask,callback(screen,data->{JSONObject value=(JSONObject)data;
            if(value.optBoolean("accepted",false)){discardClip();showSession(value.optJSONObject("session"));notice("Recording saved. You can add another task or finish this session.",false);}
            else{notice("This recording did not pass the quality check. Try another recording, or review the quality feedback below.",true);JSONObject result=value.optJSONObject("result");if(result!=null)showQuality(result,body);button(body,"Record again",false,()->{discardClip();showLiveChoice();});}
        }));});
    }
    private void showQuality(JSONObject result,LinearLayout parent){JSONObject quality=result.optJSONObject("quality");if(quality==null)quality=result;String decision=quality.optString("decision",quality.optString("status","Needs another recording"));parent.addView(DarkUi.text(this,"Recording quality: "+decision,14,DarkUi.MUTED));for(String key:new String[]{"messages","issues","warnings"})appendMessages(parent,quality.optJSONArray(key));}
    private void appendMessages(LinearLayout parent,JSONArray messages){if(messages==null)return;for(int i=0;i<messages.length();i++){Object value=messages.opt(i);String message=value instanceof JSONObject?((JSONObject)value).optString("message",((JSONObject)value).optString("reason","")):value instanceof String?(String)value:"";if(!message.trim().isEmpty())parent.addView(DarkUi.text(this,message,13,DarkUi.MUTED));}}
    private void showHistory(){page("history","Your history","Your saved recordings and daily check-ins.",true);working("Loading sessions…");api.get("/sessions",callback(screen,data->{JSONArray list=(JSONArray)data;if(list.length()==0){card("No sessions yet","Start the Live Checker or add a daily check-in to build your personal history.");return;}for(int i=0;i<list.length();i++){JSONObject s=list.optJSONObject(i);if(s==null)continue;LinearLayout c=card(formatDate(s.optString("created_at")),sessionStatus(s)+" • "+moduleSummary(s));String id=s.optString("id");button(c,s.optBoolean("has_report")?"Open report":"Open session",false,()->openSession(id));}}));}
    private void openSession(String id){page("session","Personal session","Loading your saved details…",true);working("Loading session…");api.get("/sessions/"+id,callback(screen,data->showSession((JSONObject)data)));}
    private void showSession(JSONObject session){
        if(session==null){showHistory();return;}String id=session.optString("id");boolean complete=session.optString("status").equals("completed")||session.optString("status").equals("complete");
        if(!complete)draftId=id;else if(id.equals(draftId))draftId=null;
        page("session",complete?"Saved session":"Session in progress",formatDate(session.optString("created_at"))+" • "+sessionStatus(session),true);
        card("Saved in this session",moduleSummary(session));
        if(!complete){button(body,"Add another live recording",true,()->showLiveChoice());button(body,"Add activities and notes",false,()->showCheckIn());button(body,"Finish and view report",true,()->{
            working("Preparing your personal report…");api.post("/sessions/"+id+"/complete",new JSONObject(),callback(screen,data->{if(id.equals(draftId))draftId=null;showReport(id);}));
        });}
        if(session.optBoolean("has_report")||complete)button(body,"View report",true,()->showReport(id));
        body.addView(DarkUi.text(this,"Recordings and check-ins are linked only to your patient account.",13,DarkUi.MUTED));
    }
    private void showCheckIn(){
        page("checkin","Daily check-in","Tell us how everyday activities feel today. Each item uses your own 0–4 rating.",true);
        LinearLayout c=card("Your activities","0 = no difficulty • 1 = slight • 2 = moderate • 3 = marked • 4 = unable without help");Map<String,SeekBar> ratings=new LinkedHashMap<>();
        for(int i=0;i<ACTIVITY_KEYS.length;i++){final String name=ACTIVITY_NAMES[i];TextView label=DarkUi.text(this,name+": 0",15,DarkUi.TEXT);c.addView(label);SeekBar slider=new SeekBar(this);slider.setMax(4);slider.setProgress(0);slider.setProgressTintList(android.content.res.ColorStateList.valueOf(DarkUi.ACCENT));slider.setThumbTintList(android.content.res.ColorStateList.valueOf(DarkUi.ACCENT));slider.setContentDescription(name+" difficulty rating, 0 to 4");c.addView(slider,new LinearLayout.LayoutParams(-1,DarkUi.dp(this,48)));slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar s,int value,boolean user){label.setText(name+": "+value);}public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){}});ratings.put(ACTIVITY_KEYS[i],slider);}
        EditText other=DarkUi.input(this,"Other difficulty (optional)",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);c.addView(other);
        LinearLayout n=card("Your notes","Describe anything you want to remember about today.");EditText note=DarkUi.input(this,"Personal note (optional)",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);note.setMinLines(3);n.addView(note);
        button(body,"Save check-in",true,()->{
            String noteText=note.getText().toString().trim();if(other.getText().toString().length()>2000){notice("Other difficulty must contain at most 2,000 characters.",true);return;}if((!noteText.isEmpty()&&noteText.length()<3)||noteText.length()>5000){notice("Notes must contain 3 to 5,000 characters.",true);return;}
            try{JSONObject responses=new JSONObject();for(Map.Entry<String,SeekBar> entry:ratings.entrySet())responses.put(entry.getKey(),entry.getValue().getProgress());JSONObject payload=new JSONObject().put("responses",responses).put("other_difficulty",other.getText().toString().trim());working("Saving your check-in…");ensureDraft(id->{working("Saving your activities…");api.post("/sessions/"+id+"/activities",payload,callback(screen,data->{
                if(noteText.isEmpty()){showSession((JSONObject)data);notice("Your check-in was saved.",false);}
                else try{working("Saving your note…");api.post("/sessions/"+id+"/notes",new JSONObject().put("text",noteText),callback(screen,value->{showSession((JSONObject)value);notice("Your activities and note were saved.",false);}));}catch(Exception e){notice("Activities saved, but the note could not be prepared. You can add it again.",true);}
            }));});}catch(Exception e){notice("Check your activities and try again.",true);}
        });
    }
    private void showReport(String id){
        page("report","Your personal report","Technical measurements and your own check-in information.",true);working("Loading report…");api.get("/sessions/"+id+"/report",callback(screen,data->{
            JSONObject report=(JSONObject)data;
            if(report.optBoolean("outdated"))notice("This report predates changes to the session. Finish the session again to refresh it.",true);
            card("Overview",report.optString("patient_summary","Your saved measurements appear below."));
            JSONArray sections=report.optJSONArray("sections");
            if(sections!=null)for(int i=0;i<sections.length();i++){
                JSONObject section=sections.optJSONObject(i);if(section==null)continue;
                LinearLayout c=card(section.optString("title","Recording"),section.optBoolean("accepted")?"Accepted recording or response":"Repeat or review needed");
                JSONObject quality=section.optJSONObject("quality");if(quality!=null)appendMessages(c,quality.optJSONArray("messages"));
                JSONArray measurements=section.optJSONArray("measurements");if(measurements!=null)for(int j=0;j<measurements.length();j++){
                    JSONObject item=measurements.optJSONObject(j);if(item==null)continue;
                    String unit=item.optString("unit","");String line=item.optString("label","Measurement")+": "+formatValue(item.opt("value"))+" "+unit;
                    if(item.has("reference")&&!item.isNull("reference"))line+="\nEarlier reference: "+formatValue(item.opt("reference"))+" "+unit;
                    if(item.has("delta")&&!item.isNull("delta"))line+="\nDifference: "+formatValue(item.opt("delta"))+" "+unit;
                    c.addView(DarkUi.text(this,line,15,DarkUi.TEXT));
                }
                JSONArray responses=section.optJSONArray("responses");if(responses!=null&&responses.length()>0){c.addView(DarkUi.title(this,"Your activity ratings",16));for(int j=0;j<responses.length();j++){JSONObject response=responses.optJSONObject(j);if(response!=null)c.addView(DarkUi.text(this,response.optString("label",response.optString("name","Activity"))+": "+response.optInt("value")+" / 4 — "+response.optString("description",""),14,DarkUi.TEXT));}}
                String note=section.optString("patient_note","");if(!note.trim().isEmpty())c.addView(DarkUi.text(this,"Your note: "+note,14,DarkUi.TEXT));
                JSONArray entities=section.optJSONArray("reported_entities");if(entities!=null&&entities.length()>0){c.addView(DarkUi.title(this,"Your description mentioned",16));for(int j=0;j<entities.length();j++){JSONObject entity=entities.optJSONObject(j);if(entity==null)continue;String text=entity.optString("activity","").replace('_',' ')+" • "+entity.optString("status","").replace('_',' ');String excerpt=entity.optString("source_excerpt","");if(!excerpt.trim().isEmpty())text+="\nYour words: "+excerpt;c.addView(DarkUi.text(this,text,14,DarkUi.TEXT));}c.addView(DarkUi.text(this,"These are dictionary readings of your words. Check that they match what you meant.",13,DarkUi.MUTED));}
                appendLimitations(c,section.opt("limitations"));
            }
            card("Comparison",report.optString("comparison_note",""));card("Recording coverage",report.optString("coverage_note",""));LinearLayout limits=card("Understanding these results",null);appendLimitations(limits,report.opt("limitations"));limits.addView(DarkUi.text(this,"These measurements support personal tracking. They do not diagnose Parkinson’s or determine treatment.",13,DarkUi.MUTED));
        }));
    }
    private void appendLimitations(LinearLayout parent,Object value){if(value instanceof JSONArray){JSONArray items=(JSONArray)value;for(int i=0;i<items.length();i++)parent.addView(DarkUi.text(this,items.optString(i),13,DarkUi.MUTED));}else if(value!=null&&value!=JSONObject.NULL&&!value.toString().trim().isEmpty())parent.addView(DarkUi.text(this,value.toString(),13,DarkUi.MUTED));}
    private String formatValue(Object value){if(value==null||value==JSONObject.NULL)return "Unavailable";if(value instanceof Number)return String.format(Locale.ROOT,"%.3f",((Number)value).doubleValue()).replaceAll("0+$","").replaceAll("\\.$","");return value.toString();}
    private void showAccount(){
        page("account","Your account","Private access to your own recordings and check-ins.",true);LinearLayout c=card(profile==null?"Patient account":profile.optString("full_name","Patient account"),profile==null?"":profile.optString("email",""));if(profile!=null)c.addView(DarkUi.text(this,"Preferred language: "+profile.optString("language","English"),14,DarkUi.MUTED));
        button(body,"Personal monitoring consent",false,()->showConsent());
        card("Privacy","Live recording quality is analysed on this phone. A recording is uploaded only when you choose Upload. Account tokens are encrypted with Android Keystore; this app does not include a password or shared login.");
        button(body,"Server connection",false,()->showServer());button(body,"Refresh account",false,()->loadProfile());button(body,"Logout",false,()->{
            working("Signing out…");api.post("/auth/logout",new JSONObject(),new ApiClient.Callback(){public void success(Object data){localLogout();}public void failure(int code,String message){localLogout();notice("Signed out on this phone. Server revocation could not be confirmed.",true);}});
        store.clear();discardClip();
        });body.addView(DarkUi.text(this,"Android preview 0.3.0 • Patient application",12,DarkUi.MUTED));
    }
    private void showConsent(){
        page("consent","Personal consent","Choose whether your recordings and check-ins may be stored for your own monitoring.",true);working("Loading consent…");api.get("/profile",callback(screen,data->{profile=(JSONObject)data;JSONObject consent=profile.optJSONObject("monitoring_consent");boolean active=consent!=null&&consent.optBoolean("active");card("Current choice",active?"Personal monitoring consent is active.":"Personal monitoring consent is not active.");card("Your choice","Live signal checks run on this phone. Uploading a clip sends it to your configured patient server. Withdrawing consent stops new saved monitoring; it does not automatically delete existing records.");button(body,active?"Withdraw personal consent":"Accept personal consent",!active,()->{try{working("Saving your consent…");api.post("/profile/consent",new JSONObject().put("acknowledged",!active),callback(screen,value->{showAccount();notice("Your consent choice was saved.",false);}));}catch(Exception e){notice("Your choice could not be prepared.",true);}});}));
    }
    private void localLogout(){api.invalidate();store.clear();discardClip();draftId=null;profile=null;showAuth(false);}
    private void showServer(){
        page("server","Server connection","For the local preview, keep your phone and laptop on the same Wi-Fi.",false);LinearLayout c=card("Patient server address","Example: http://192.168.1.11:8767\nFor a public server, use HTTPS with a valid certificate.");EditText input=DarkUi.input(this,"Server address",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);input.setSingleLine(true);input.setText(store.server());c.addView(input);
        button(c,"Save server",true,()->{try{String address=ServerAddress.validate(input.getText().toString());if(address.equals(store.server())){if(store.token()==null)showAuth(false);else showDashboard();return;}new AlertDialog.Builder(this).setTitle("Change server?").setMessage("You will be signed out on this phone. Your next login will use the new server.").setNegativeButton("Cancel",(d,w)->{}).setPositiveButton("Save",(d,w)->{api.invalidate();store.setServer(address);discardClip();draftId=null;profile=null;showAuth(false);notice("Server saved. Login or register to continue.",false);}).show();}catch(IllegalArgumentException e){notice(e.getMessage(),true);}});
        button(body,"Back",false,()->{if(store.token()==null)showAuth(false);else showAccount();});body.addView(DarkUi.text(this,"Local Wi-Fi HTTP is intended for your private preview network. Choose a trusted HTTPS server for remote access.",13,DarkUi.MUTED));
    }
    private String taskName(String code){for(int i=0;i<VIDEO_TASKS.length;i++)if(VIDEO_TASKS[i].equals(code))return VIDEO_NAMES[i];for(int i=0;i<AUDIO_TASKS.length;i++)if(AUDIO_TASKS[i].equals(code))return AUDIO_NAMES[i];return "Recording";}
    private String formatDate(String date){return date.replace('T',' ').replace("+00:00"," UTC").replace("Z"," UTC");}
    private String sessionStatus(JSONObject session){String state=session.optString("status","draft");return state.equals("completed")||state.equals("complete")?"Complete":"In progress";}
    private String moduleName(String task){if(task.equals("adl"))return "Daily activities";if(task.equals("nlp"))return "Personal notes";if(task.startsWith("voice_"))return taskName(task.substring(6));if(task.equals("voice"))return "Voice recording";return taskName(task);}
    private String moduleSummary(JSONObject session){Object modules=session.opt("modules");List<String> names=new ArrayList<>();if(modules instanceof JSONArray){JSONArray list=(JSONArray)modules;for(int i=0;i<list.length();i++)names.add(moduleName(list.optString(i)));}else if(modules instanceof JSONObject){JSONObject object=(JSONObject)modules;java.util.Iterator<String> keys=object.keys();while(keys.hasNext())names.add(moduleName(keys.next()));}return names.isEmpty()?"No recordings or check-ins saved yet":TextUtils.join(" · ",names);}
}
