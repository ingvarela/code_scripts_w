// g++ -std=c++17 main_client_full.cpp -o st_cam_client \
//   `pkg-config --cflags --libs elementary ewebkit2` \
//   -lcurl -lcjson -lsmartthings-client
//
// In Tizen Studio, use this as your main.cpp. Adjust CLIENT_ID, CLIENT_SECRET, REDIRECT_URI.
//
// Privileges (manifest):
// <privilege>http://tizen.org/privilege/internet</privilege>
// <privilege>http://tizen.org/privilege/mediastorage</privilege>

#include <smartthings_client.h>
#include <Elementary.h>
#include <EWebKit2.h>
#include <curl/curl.h>
#include <cjson/cJSON.h>
#include <app_common.h>
#include <dlog.h>

#include <string>
#include <vector>
#include <fstream>
#include <stdexcept>
#include <unistd.h>

#define LOG_TAG "STCLIENT"

// ---------- CONFIG ----------
static const char* CLIENT_ID     = "YOUR_CLIENT_ID";
static const char* CLIENT_SECRET = "YOUR_CLIENT_SECRET";
static const char* REDIRECT_URI  = "YOUR_REGISTERED_REDIRECT_URI";
static const char* SCOPES        = "r:devices:* x:devices:*";
static const char* AUTH_BASE     = "https://auth-global.api.smartthings.com/oauth/authorize";
static const char* TOKEN_URL     = "https://auth-global.api.smartthings.com/oauth/token";
static const char* API_BASE      = "https://api.smartthings.com/v1";
// ----------------------------

// ----------- CURL HELPERS -----------
struct Buf { std::string data; };
static size_t write_cb(void* ptr, size_t s, size_t n, void* ud){ ((Buf*)ud)->data.append((const char*)ptr,s*n); return s*n; }
static void curl_check(CURLcode rc, const char* w){ if(rc!=CURLE_OK){ dlog_print(DLOG_ERROR,LOG_TAG,"%s: %s",w,curl_easy_strerror(rc)); throw std::runtime_error("curl"); } }
static std::string http_post_form(const std::string& url,const std::vector<std::pair<std::string,std::string>>& form,const std::string& u="",const std::string& p=""){
  CURL* c=curl_easy_init(); if(!c) throw std::runtime_error("curl init"); Buf b;
  curl_easy_setopt(c,CURLOPT_URL,url.c_str()); curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,write_cb); curl_easy_setopt(c,CURLOPT_WRITEDATA,&b);
  curl_easy_setopt(c,CURLOPT_POST,1L); curl_easy_setopt(c,CURLOPT_SSL_VERIFYPEER,1L);
  std::string body; for(size_t i=0;i<form.size();++i){ char* k=curl_easy_escape(c,form[i].first.c_str(),0); char* v=curl_easy_escape(c,form[i].second.c_str(),0); if(i) body+="&"; body+=k; body+="="; body+=v; curl_free(k); curl_free(v);}
  curl_easy_setopt(c,CURLOPT_POSTFIELDS,body.c_str());
  struct curl_slist* h=nullptr; h=curl_slist_append(h,"Content-Type: application/x-www-form-urlencoded"); curl_easy_setopt(c,CURLOPT_HTTPHEADER,h);
  if(!u.empty()){ std::string up=u+":"+p; curl_easy_setopt(c,CURLOPT_HTTPAUTH,CURLAUTH_BASIC); curl_easy_setopt(c,CURLOPT_USERPWD,up.c_str()); }
  CURLcode rc=curl_easy_perform(c); curl_check(rc,"POST"); curl_slist_free_all(h); curl_easy_cleanup(c); return b.data;
}
static std::string http_get_json(const std::string& url,const std::string& bearer){
  CURL* c=curl_easy_init(); if(!c) throw std::runtime_error("curl init"); Buf b;
  curl_easy_setopt(c,CURLOPT_URL,url.c_str()); curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,write_cb); curl_easy_setopt(c,CURLOPT_WRITEDATA,&b); curl_easy_setopt(c,CURLOPT_SSL_VERIFYPEER,1L);
  struct curl_slist* h=nullptr; std::string a="Authorization: Bearer "+bearer; h=curl_slist_append(h,a.c_str()); h=curl_slist_append(h,"Accept: application/json"); curl_easy_setopt(c,CURLOPT_HTTPHEADER,h);
  CURLcode rc=curl_easy_perform(c); curl_check(rc,"GET"); curl_slist_free_all(h); curl_easy_cleanup(c); return b.data;
}
static std::string http_post_json(const std::string& url,const std::string& bearer,const std::string& json){
  CURL* c=curl_easy_init(); if(!c) throw std::runtime_error("curl init"); Buf b;
  curl_easy_setopt(c,CURLOPT_URL,url.c_str()); curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,write_cb); curl_easy_setopt(c,CURLOPT_WRITEDATA,&b); curl_easy_setopt(c,CURLOPT_SSL_VERIFYPEER,1L);
  curl_easy_setopt(c,CURLOPT_POST,1L); curl_easy_setopt(c,CURLOPT_POSTFIELDS,json.c_str());
  struct curl_slist* h=nullptr; std::string a="Authorization: Bearer "+bearer; h=curl_slist_append(h,a.c_str()); h=curl_slist_append(h,"Content-Type: application/json; charset=utf-8");
  curl_easy_setopt(c,CURLOPT_HTTPHEADER,h);
  CURLcode rc=curl_easy_perform(c); curl_check(rc,"POST JSON"); curl_slist_free_all(h); curl_easy_cleanup(c); return b.data;
}
static void http_download_binary(const std::string& url,const char* path){
  CURL* c=curl_easy_init(); if(!c) throw std::runtime_error("curl init"); FILE* fp=fopen(path,"wb"); if(!fp) throw std::runtime_error("fopen");
  curl_easy_setopt(c,CURLOPT_URL,url.c_str()); curl_easy_setopt(c,CURLOPT_WRITEDATA,fp); curl_easy_setopt(c,CURLOPT_SSL_VERIFYPEER,1L);
  CURLcode rc=curl_easy_perform(c); curl_check(rc,"DOWNLOAD"); curl_easy_cleanup(c); fclose(fp);
}
// ----------------------------------

// ---------- TOKEN HANDLING ----------
struct Tokens { std::string access; std::string refresh; };
static std::string path_join(const std::string& a,const std::string& b){ return a.back()=='/'?a+b:a+"/"+b; }
static bool save_tokens(const std::string& dir,const Tokens& t){ std::ofstream f(path_join(dir,"tokens.json")); if(!f.good()) return false; f<<"{\"access_token\":\""<<t.access<<"\",\"refresh_token\":\""<<t.refresh<<"\"}"; return true; }
static bool load_tokens(const std::string& dir,Tokens& t){ std::ifstream f(path_join(dir,"tokens.json")); if(!f.good()) return false; std::string d((std::istreambuf_iterator<char>(f)),{}); cJSON* r=cJSON_Parse(d.c_str()); if(!r) return false; auto* a=cJSON_GetObjectItem(r,"access_token"); auto* rtk=cJSON_GetObjectItem(r,"refresh_token"); if(a&&cJSON_IsString(a)) t.access=a->valuestring; if(rtk&&cJSON_IsString(rtk)) t.refresh=rtk->valuestring; cJSON_Delete(r); return !t.refresh.empty(); }
static Tokens token_exchange(const std::string& code){ auto r=http_post_form(TOKEN_URL,{{"grant_type","authorization_code"},{"code",code},{"redirect_uri",REDIRECT_URI}},CLIENT_ID,CLIENT_SECRET); cJSON* j=cJSON_Parse(r.c_str()); if(!j) throw std::runtime_error("bad token json"); Tokens t; t.access=cJSON_GetObjectItem(j,"access_token")->valuestring; auto* rr=cJSON_GetObjectItem(j,"refresh_token"); if(rr&&cJSON_IsString(rr)) t.refresh=rr->valuestring; cJSON_Delete(j); return t; }
static Tokens token_refresh(const std::string& refresh){ auto r=http_post_form(TOKEN_URL,{{"grant_type","refresh_token"},{"refresh_token",refresh},{"redirect_uri",REDIRECT_URI}},CLIENT_ID,CLIENT_SECRET); cJSON* j=cJSON_Parse(r.c_str()); if(!j) throw std::runtime_error("bad refresh json"); Tokens t; t.access=cJSON_GetObjectItem(j,"access_token")->valuestring; auto* rr=cJSON_GetObjectItem(j,"refresh_token"); if(rr&&cJSON_IsString(rr)) t.refresh=rr->valuestring; cJSON_Delete(j); return t; }
// -----------------------------------

// ---------- SMARTTHINGS REST ----------
struct Device { std::string id,name; bool hasImage=false; };
static bool has_img(const std::string& tk,const std::string& id){ try{ auto s=http_get_json(std::string(API_BASE)+"/devices/"+id+"/status",tk); return s.find("\"imageCapture\"")!=std::string::npos; }catch(...){return false;} }
static std::vector<Device> list_devices(const std::string& tk){ std::vector<Device> v; auto r=http_get_json(std::string(API_BASE)+"/devices",tk); cJSON* j=cJSON_Parse(r.c_str()); if(!j) return v; cJSON* items=cJSON_GetObjectItem(j,"items"); if(items&&cJSON_IsArray(items)){ cJSON* it; cJSON_ArrayForEach(it,items){ auto* id=cJSON_GetObjectItem(it,"deviceId"); auto* nm=cJSON_GetObjectItem(it,"name"); if(id&&nm&&cJSON_IsString(id)&&cJSON_IsString(nm)){ Device d; d.id=id->valuestring; d.name=nm->valuestring; d.hasImage=has_img(tk,d.id); v.push_back(d); } } } cJSON_Delete(j); return v; }
static void take_image(const std::string& tk,const std::string& id){ std::string url=std::string(API_BASE)+"/devices/"+id+"/commands"; std::string body=R"({"commands":[{"component":"main","capability":"imageCapture","command":"take","arguments":[]}]} )"; http_post_json(url,tk,body); }
static std::string find_snapshot(const std::string& tk,const std::string& id){ auto s=http_get_json(std::string(API_BASE)+"/devices/"+id+"/status",tk); cJSON* j=cJSON_Parse(s.c_str()); if(!j) return ""; auto pick=[&](const char*c,const char*a){ auto* comps=cJSON_GetObjectItem(j,"components"); if(!comps) return (cJSON*)nullptr; auto* main=cJSON_GetObjectItem(comps,"main"); if(!main) return (cJSON*)nullptr; auto* cap=cJSON_GetObjectItem(main,c); if(!cap) return (cJSON*)nullptr; auto* attr=cJSON_GetObjectItem(cap,a); return attr; }; std::string url; for(auto&p:{std::pair<const char*,const char*>{"imageCapture","imageUrl"},{"imageCapture","image"},{"camera","image"}}){ auto* a=pick(p.first,p.second); if(a&&cJSON_IsObject(a)){ auto* v=cJSON_GetObjectItem(a,"value"); if(v&&cJSON_IsString(v)) {url=v->valuestring; break;} } } cJSON_Delete(j); return url; }
// --------------------------------------

// ---------- SMARTTHINGS CLIENT SDK ----------
struct STClient{ smartthings_client_h h{}; bool connected=false; };
static void status_cb(smartthings_client_h,smartthings_client_status_e st,void* ud){ ((STClient*)ud)->connected=(st==SMARTTHINGS_CLIENT_STATUS_CONNECTED); dlog_print(DLOG_INFO,LOG_TAG,"ST Client status=%d",st); }
static void conn_cb(smartthings_client_h,bool c,void*ud){ ((STClient*)ud)->connected=c; dlog_print(DLOG_INFO,LOG_TAG,"Connection=%d",c); }
static void init_client(STClient&ctx){ int r=smartthings_client_initialize(&ctx.h,status_cb,&ctx); if(r!=SMARTTHINGS_CLIENT_ERROR_NONE){dlog_print(DLOG_ERROR,LOG_TAG,"init fail %d",r);return;} smartthings_client_set_connection_status_cb(ctx.h,conn_cb,&ctx); r=smartthings_client_start(ctx.h); if(r==SMARTTHINGS_CLIENT_ERROR_NONE)dlog_print(DLOG_INFO,LOG_TAG,"Client started"); }
static void deinit_client(STClient&ctx){ if(!ctx.h)return; smartthings_client_stop(ctx.h); smartthings_client_deinitialize(ctx.h); ctx.h=nullptr; }
// --------------------------------------------

// ---------- EFL UI ----------
struct App {
  Evas_Object* win{};
  Evas_Object* box{};
  Evas_Object* btnAuth{};
  Evas_Object* btnList{};
  Evas_Object* btnCap{};
  Evas_Object* list{};
  Evas_Object* img{};
  Evas_Object* web{};

  std::string dataDir;
  std::string imgPath;
  Tokens tok;
  std::vector<Device> devs;
  int sel=-1;
};

static char* gl_text(void* data,Evas_Object*,const char*){auto*d=(Device*)data; std::string s=d->name+(d->hasImage?" [imageCapture]":""); return strdup(s.c_str());}
static void gl_sel(void*data,Evas_Object*,void*it){((App*)data)->sel=elm_genlist_item_index_get((Elm_Object_Item*)it)-1;}
static std::string urlenc(CURL*c,const std::string&s){char*e=curl_easy_escape(c,s.c_str(),0);std::string r=e?e:"";if(e)curl_free(e);return r;}
static std::string auth_url(){CURL*c=curl_easy_init();auto u=std::string(AUTH_BASE)+"?response_type=code&client_id="+urlenc(c,CLIENT_ID)+"&redirect_uri="+urlenc(c,REDIRECT_URI)+"&scope="+urlenc(c,SCOPES);curl_easy_cleanup(c);return u;}

static Eina_Bool nav_cb(Evas_Object*,Ewk_Policy_Decision*d,Ewk_Policy_Navigation_Type, Ewk_Frame_Ref*,void*ud){
  auto*a=(App*)ud; const char* u=ewk_policy_decision_url_get(d); if(!u) return EINA_FALSE; std::string s=u;
  if(s.rfind(REDIRECT_URI,0)==0){ auto p=s.find("code="); if(p!=std::string::npos){ auto code=s.substr(p+5); auto amp=code.find('&'); if(amp!=std::string::npos)code=code.substr(0,amp);
      try{ a->tok=token_exchange(code); save_tokens(a->dataDir,a->tok); elm_object_text_set(a->btnAuth,"Authorized ✓"); evas_object_hide(a->web);}catch(const std::exception&e){dlog_print(DLOG_ERROR,LOG_TAG,"Auth err %s",e.what());}} ewk_policy_decision_ignore(d); return EINA_TRUE;}
  ewk_policy_decision_use(d); return EINA_TRUE;
}

static void refresh_preview(App*a){ if(a->imgPath.empty())return; evas_object_image_file_set(a->img,a->imgPath.c_str(),nullptr); evas_object_show(a->img); }

static void btn_auth(void*d,Evas_Object*,void*){auto*a=(App*)d; if(!a->tok.access.empty()){elm_object_text_set(a->btnAuth,"Authorized ✓");return;} evas_object_show(a->web); ewk_view_url_set(a->web,auth_url().c_str());}
static void btn_list(void*d,Evas_Object*,void*){auto*a=(App*)d; if(a->tok.access.empty())return; a->devs=list_devices(a->tok.access); elm_genlist_clear(a->list);
  static Elm_Genlist_Item_Class itc; memset(&itc,0,sizeof(itc)); itc.item_style="default"; itc.func.text_get=gl_text;
  for(auto&x:a->devs) elm_genlist_item_append(a->list,&itc,&x,nullptr,ELM_GENLIST_ITEM_NONE,gl_sel,a);
}
static void btn_cap(void*d,Evas_Object*,void*){auto*a=(App*)d; if(a->tok.access.empty()||a->devs.empty())return; int i=a->sel; if(i<0||i>=(int)a->devs.size()) for(size_t j=0;j<a->devs.size();++j) if(a->devs[j].hasImage){i=j;break;}
  if(i<0)return; auto&dv=a->devs[i]; if(!dv.hasImage)return; take_image(a->tok.access,dv.id); std::string url; for(int r=0;r<10;++r){ usleep(500000); url=find_snapshot(a->tok.access,dv.id); if(!url.empty())break;}
  if(url.empty()){ dlog_print(DLOG_INFO,LOG_TAG,"No snapshot URL."); return; } http_download_binary(url,a->imgPath.c_str()); refresh_preview(a); }

static void try_refresh(App*a){Tokens t;if(!load_tokens(a->dataDir,t))return; try{Tokens n=token_refresh(t.refresh); if(n.refresh.empty())n.refresh=t.refresh; a->tok=n; save_tokens(a->dataDir,n); elm_object_text_set(a->btnAuth,"Authorized ✓");}catch(...){;}}

EAPI_MAIN int elm_main(int,char**){
  curl_global_init(CURL_GLOBAL_DEFAULT);
  STClient ctx; init_client(ctx);

  App a; char*p=app_get_data_path(); a.dataDir=p?p:"/tmp/"; if(p)free(p); a.imgPath=path_join(a.dataDir,"capture.jpg");

  a.win=elm_win_util_standard_add("stcam","SmartThings Camera");
  elm_win_autodel_set(a.win,EINA_TRUE);
  a.box=elm_box_add(a.win); evas_object_size_hint_weight_set(a.box,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND); elm_win_resize_object_add(a.win,a.box); evas_object_show(a.box);

  a.btnAuth=elm_button_add(a