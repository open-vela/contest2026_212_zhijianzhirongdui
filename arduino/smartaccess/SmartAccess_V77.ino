#include <esp_camera.h>
#include <Smart_Access_Control_inferencing.h>
#include <Wire.h>
#include "SSD1306Wire.h"
#include <ESP32Servo.h>
#include <NewPing.h>
#include <Adafruit_NeoPixel.h>
#include "edge-impulse-sdk/dsp/image/image.hpp"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "time.h"
#include <HTTPClient.h>
#include <ArduinoUZlib.h> // ✨ 引入解压神器

// ==========================================
// 1. 网络与云平台配置 (请修改为您自己的凭证)
// ==========================================
const char* WIFI_SSID = "<YOUR_WIFI_SSID>";
const char* WIFI_PASSWORD = "<YOUR_WIFI_PASSWORD>";

const char* MQTT_SERVER = "bemfa.com";
const int   MQTT_PORT = 9501;
const char* MQTT_CLIENT_ID = "<YOUR_BEMFA_CLIENT_ID>";
const char* MQTT_TOPIC = "SmartDoor";

// ==========================================
// 1.5 和风天气 (QWeather) API 配置
// ==========================================
const char* QWEATHER_API_KEY = "de3975e2fdd5479f80c7af764635d1ac";
const char* QWEATHER_HOST = "nr2pg7wprd.re.qweatherapi.com";

const char* ntpServer = "ntp.aliyun.com";
const long  gmtOffset_sec = 8 * 3600;
const int   daylightOffset_sec = 0;

String WEATHER_LOCATION = "沈阳";
String locationID = "";
String currentLat = "";
String currentLon = "";
String currentTemp = "--°C";
String currentAqi = "--";
unsigned long lastWeatherSyncTime = 0;

int currentWeatherCode = 0;

// 【增强】多预警管理结构体
struct WarningInfo {
    int level;    // 1=蓝, 2=黄, 3=橙, 4=红
    int iconCode; // 映射到的赛博图标ID
    String name;  // 全大写英文简称
};
WarningInfo activeWarnings[15]; // 放宽到15个预警解析池
int activeWarningCount = 0;

// ==========================================
// 2. 核心业务逻辑参数
// ==========================================
float AI_MATCH_THRESHOLD = 0.70;
int FACE_DETECTION_THRESHOLD = 2;
unsigned long RECOGNITION_TIMEOUT_MS = 60000;
int AUTO_CLOSE_TIME_SEC = 10;
float WAKEUP_DISTANCE_CM = 50.0;
int LED_BRIGHTNESS = 30;

int LED_BASE_R = 0;
int LED_BASE_G = 100;
int LED_BASE_B = 255;

String bannedUsers = "";

// ==========================================
// 硬件引脚定义
// ==========================================
#define TRIG_PIN D2
#define ECHO_PIN D3
#define MAX_DISTANCE 200

#define SERVO_PIN D1
#define SERVO_STOP 95
#define SERVO_OPEN_SPEED 125
#define SERVO_CLOSE_SPEED 65

#define STRIP_PIN D0
#define NUM_LEDS 12

// XIAO ESP32S3 Sense 摄像头引脚
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39
#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

#define EI_CAMERA_RAW_FRAME_BUFFER_COLS           320
#define EI_CAMERA_RAW_FRAME_BUFFER_ROWS           240
#define EI_CAMERA_FRAME_BYTE_SIZE                 3

enum SystemState {
    STATE_SLEEP,
    STATE_WAKEUP,
    STATE_RECOGNIZING,
    STATE_SUCCESS,
    STATE_FAILED
};
SystemState currentState = STATE_SLEEP;

SSD1306Wire display(0x3c, D4, D5);
Servo doorServo;
NewPing sonar(TRIG_PIN, ECHO_PIN, MAX_DISTANCE);
Adafruit_NeoPixel strip = Adafruit_NeoPixel(NUM_LEDS, STRIP_PIN, NEO_GRB + NEO_KHZ800);

WiFiClient espClient;
PubSubClient mqtt(espClient);
unsigned long lastMqttReconnectAttempt = 0;

unsigned long recognizingStartTime = 0;
int faceDetectionCount = 0;

String lastRecognizedUser = "";
uint8_t *snapshot_buf;
static bool is_initialised = false;

static camera_config_t camera_config = {
    .pin_pwdn = PWDN_GPIO_NUM,
    .pin_reset = RESET_GPIO_NUM,
    .pin_xclk = XCLK_GPIO_NUM,
    .pin_sscb_sda = SIOD_GPIO_NUM,
    .pin_sscb_scl = SIOC_GPIO_NUM,
    .pin_d7 = Y9_GPIO_NUM,
    .pin_d6 = Y8_GPIO_NUM,
    .pin_d5 = Y7_GPIO_NUM,
    .pin_d4 = Y6_GPIO_NUM,
    .pin_d3 = Y5_GPIO_NUM,
    .pin_d2 = Y4_GPIO_NUM,
    .pin_d1 = Y3_GPIO_NUM,
    .pin_d0 = Y2_GPIO_NUM,
    .pin_vsync = VSYNC_GPIO_NUM,
    .pin_href = HREF_GPIO_NUM,
    .pin_pclk = PCLK_GPIO_NUM,
    .xclk_freq_hz = 20000000,
    .ledc_timer = LEDC_TIMER_0,
    .ledc_channel = LEDC_CHANNEL_0,
    .pixel_format = PIXFORMAT_JPEG,
    .frame_size = FRAMESIZE_QVGA,
    .jpeg_quality = 12,
    .fb_count = 1,
    .fb_location = CAMERA_FB_IN_PSRAM,
    .grab_mode = CAMERA_GRAB_WHEN_EMPTY,
};

// ==========================================
// 辅助函数
// ==========================================

// 【核心字典映射】将 QWeather Type Code 转换为本地赛博图标 ID
int mapWarningTypeToIcon(int type) {
    if (type == 1001 || type == 1049 || type == 1055 || type == 1803 || type == 2330 || type == 2423) return 12; // 台风
    if (type == 1003 || type == 1038 || type == 1064 || type == 2502 || type == 1609 || type == 1804 || type == 2084 || type == 2135) return 3; // 暴雨
    if (type == 1004 || type == 1033 || type == 1040 || type == 2052 || type == 2079 || type == 2133 || type == 2168 || type == 2215) return 4; // 暴雪
    if (type == 1005 || type == 1039 || type == 1050 || type == 1059 || type == 1607 || type == 2082 || type == 2122) return 5; // 寒潮
    if (type == 1006 || type == 1023 || type == 1062 || type == 2001 || type == 2051 || type == 2127 || type == 2150) return 6; // 大风
    if (type == 1007 || type == 1047 || type == 1051 || type == 2080 || type == 2164 || type == 2525) return 7; // 沙尘暴
    if (type == 1009 || type == 1010 || type == 1024 || type == 1601 || type == 2030 || type == 2081 || type == 2128) return 8; // 高温
    if (type == 1022 || type == 1078 || type == 1215 || type == 1217 || type == 2131) return 9; // 干旱
    if (type == 1014 || type == 1043 || type == 1054 || type == 1608 || type == 2102 || type == 2124) return 10; // 雷电
    if (type == 1015 || type == 2076 || type == 2125 || type == 2528) return 11; // 冰雹
    if (type == 1016 || type == 1610 || type == 2109 || type == 2130) return 13; // 霜冻
    if (type == 1017 || type == 1053 || type == 1065 || type == 2003 || type == 2100 || type == 2154) return 14; // 大雾
    if (type == 1021 || type == 1057 || type == 2002 || type == 2165) return 15; // 道路结冰
    if (type == 1019 || type == 1061) return 16; // 霾
    if (type == 1020 || type == 1052 || type == 1058 || type == 2200) return 17; // 雷雨大风
    if (type == 1029 || type == 1067 || type == 1074 || type == 1271 || type == 1272) return 18; // 重污染
    return 0; // 其他未知
}

// 获取规范的警告简称
String mapWarningTypeToName(int type) {
    int icon = mapWarningTypeToIcon(type);
    switch (icon) {
        case 3: return "RAIN STORM";
        case 4: return "SNOW STORM";
        case 5: return "COLD WAVE";
        case 6: return "GALE WARN";
        case 7: return "SAND STORM";
        case 8: return "HEAT WAVE";
        case 9: return "DROUGHT";
        case 10: return "LIGHTNING";
        case 11: return "HAIL WARN";
        case 12: return "TYPHOON!";
        case 13: return "FROST WARN";
        case 14: return "HEAVY FOG";
        case 15: return "ROAD ICING";
        case 16: return "HAZE WARN";
        case 17: return "THUNDER GUST";
        case 18: return "POLLUTION";
        default: return "ALERT";
    }
}

float parseJsonValue(String json, String key, float defaultVal) {
    String searchKey = "\"" + key + "\":";
    int startIdx = json.indexOf(searchKey);
    if (startIdx == -1) return defaultVal;
    startIdx += searchKey.length();

    int endIdx = json.indexOf(",", startIdx);
    if (endIdx == -1) endIdx = json.indexOf("}", startIdx);
    if (endIdx == -1) return defaultVal;

    String valStr = json.substring(startIdx, endIdx);
    valStr.replace("\"", "");
    valStr.trim();

    if (valStr.length() == 0) return defaultVal;
    return valStr.toFloat();
}

String parseJsonString(String json, String key) {
    String searchKey = "\"" + key + "\":";
    int startIdx = json.indexOf(searchKey);
    if (startIdx == -1) return "";
    startIdx += searchKey.length();

    int endIdx = json.indexOf(",", startIdx);
    if (endIdx == -1) endIdx = json.indexOf("}", startIdx);
    if (endIdx == -1) return "";

    String valStr = json.substring(startIdx, endIdx);
    valStr.replace("\"", "");
    valStr.trim();
    return valStr;
}

String urlEncode(String str) {
    String encodedString = "";
    char c;
    char code0;
    char code1;
    for (int i = 0; i < str.length(); i++) {
        c = str.charAt(i);
        if (isalnum(c)) { encodedString += c; }
        else {
            code1 = (c & 0xf) + '0';
            if ((c & 0xf) > 9) code1 = (c & 0xf) - 10 + 'A';
            c = (c >> 4) & 0xf;
            code0 = c + '0';
            if (c > 9) code0 = c - 10 + 'A';
            encodedString += '%';
            encodedString += code0;
            encodedString += code1;
        }
    }
    return encodedString;
}

// ✨✨✨ 核心：安全解压拦截引擎 ✨✨✨
String getDecompressedPayload(HTTPClient &http) {
    String rawPayload = http.getString();
    size_t size = rawPayload.length();

    if (size == 0) return "";

    // 侦测 GZIP 的标准文件头 (1F 8B)
    if (size > 2 && (uint8_t)rawPayload[0] == 0x1F && (uint8_t)rawPayload[1] == 0x8B) {
        uint8_t *outbuf = NULL;
        uint32_t outsize = 0;

        // 调用 UZlib 进行硬核解压
        int result = ArduinoUZlib::decompress((uint8_t*)rawPayload.c_str(), size, outbuf, outsize);

        if (outbuf != NULL && outsize > 0) {
            String decodedStr = "";
            decodedStr.reserve(outsize);
            for(uint32_t i = 0; i < outsize; i++) {
                decodedStr += (char)outbuf[i];
            }

            free(outbuf); // ⚠️ 极其关键！防止 ESP32 内存耗尽死机
            return decodedStr;
        }
    }
    return rawPayload;
}

// ==========================================
// 高级 UI 渲染函数库
// ==========================================
void displayMessage(const String& msg1, const String& msg2 = "") {
    display.clear();
    display.setTextAlignment(TEXT_ALIGN_CENTER);
    display.setFont(ArialMT_Plain_16);
    display.drawString(64, 15, msg1);
    if(msg2.length() > 0) {
        display.setFont(ArialMT_Plain_10);
        display.drawString(64, 40, msg2);
    }
    display.display();
}

void drawScanningUI() {
    display.clear();
    int len = 10;
    display.drawHorizontalLine(34, 10, len);
    display.drawVerticalLine(34, 10, len);
    display.drawHorizontalLine(94-len, 10, len);
    display.drawVerticalLine(94, 10, len);
    display.drawHorizontalLine(34, 54, len);
    display.drawVerticalLine(34, 54-len, len);
    display.drawHorizontalLine(94-len, 54, len);
    display.drawVerticalLine(94, 54-len, len);

    int scanY = 12 + (millis() / 30) % 40;
    display.drawHorizontalLine(38, scanY, 52);

    display.setTextAlignment(TEXT_ALIGN_CENTER);
    display.setFont(ArialMT_Plain_10);
    display.drawString(64, 25, "Scanning...");
    display.display();
}

void drawVerifyingUI(String name, int current, int total) {
    display.clear();
    display.setTextAlignment(TEXT_ALIGN_CENTER);
    display.setFont(ArialMT_Plain_16);
    display.drawString(64, 12, name);
    display.drawString(65, 12, name);

    display.setFont(ArialMT_Plain_10);
    display.drawString(64, 32, "Verifying...");

    int progress = (current * 100) / total;
    display.drawProgressBar(34, 48, 60, 6, progress);
    display.display();
}

void drawDeniedUI(String topReason) {
    display.clear();
    display.drawCircle(64, 26, 14);
    display.drawLine(57, 19, 71, 33);
    display.drawLine(71, 19, 57, 33);
    display.drawLine(58, 19, 72, 33);
    display.drawLine(72, 19, 58, 33);

    display.setTextAlignment(TEXT_ALIGN_CENTER);
    display.setFont(ArialMT_Plain_16);
    display.drawString(64, 45, "DENIED");
    display.drawString(65, 45, "DENIED");

    if (topReason.length() > 0) {
        display.setFont(ArialMT_Plain_10);
        display.drawString(64, 0, topReason);
    }
    display.display();
}

// ==========================================
// QWeather (和风天气) CMA级通讯引擎
// ==========================================
void syncWeather() {
    if (WiFi.status() == WL_CONNECTED) {
        lastWeatherSyncTime = millis();
        WiFiClientSecure secureClient;
        secureClient.setInsecure();

        HTTPClient http;
        http.setTimeout(10000);

        // -----------------------------------------------------
        // 步骤 1：GeoAPI 获取 LocationID 及经纬度 (Lat/Lon)
        // -----------------------------------------------------
        if (locationID == "") {
            String geoUrl = "https://" + String(QWEATHER_HOST) + "/geo/v2/city/lookup?location=" + urlEncode(WEATHER_LOCATION);
            Serial.println("\n>>> [1/4] Requesting GeoAPI: " + geoUrl);

            http.begin(secureClient, geoUrl);
            http.addHeader("X-QW-Api-Key", QWEATHER_API_KEY);

            int geoCode = http.GET();
            String payload = getDecompressedPayload(http);

            Serial.printf("--- GeoAPI HTTP Code: %d\n", geoCode);

            if (geoCode == 200) {
                String cid = parseJsonString(payload, "id");
                String lat = parseJsonString(payload, "lat");
                String lon = parseJsonString(payload, "lon");

                if (cid.length() > 0) {
                    locationID = cid;
                    currentLat = lat;
                    currentLon = lon;
                    Serial.println("--- GeoAPI Success! City ID: " + locationID);
                }
            } else {
                Serial.println("--- GeoAPI Parse Failed! JSON: " + payload);
            }
            http.end();
        }

        if (locationID == "") {
            Serial.println("!!! Weather Sync Aborted: Failed to get Location ID.");
            return;
        }

        // -----------------------------------------------------
        // 步骤 2：获取常规天气与温度
        // -----------------------------------------------------
        String weatherUrl = "https://" + String(QWEATHER_HOST) + "/v7/weather/now?location=" + locationID + "&lang=en";
        Serial.println("\n>>> [2/4] Requesting Weather Now...");
        http.begin(secureClient, weatherUrl);
        http.addHeader("X-QW-Api-Key", QWEATHER_API_KEY);
        int wCode = http.GET();
        String wPayload = getDecompressedPayload(http);

        if (wCode == 200) {
            int tempStart = wPayload.indexOf("\"temp\":\"");
            if (tempStart > 0) {
                tempStart += 8;
                int tempEnd = wPayload.indexOf("\"", tempStart);
                currentTemp = wPayload.substring(tempStart, tempEnd) + "°C";
            }

            String textWeather = parseJsonString(wPayload, "text");
            textWeather.toLowerCase();

            if (textWeather.indexOf("rain") >= 0 || textWeather.indexOf("shower") >= 0) currentWeatherCode = 2;
            else if (textWeather.indexOf("snow") >= 0) currentWeatherCode = 4;
            else if (textWeather.indexOf("cloud") >= 0 || textWeather.indexOf("overcast") >= 0) currentWeatherCode = 1;
            else currentWeatherCode = 0;
            Serial.println("--- Weather Parsed: " + currentTemp + ", base icon: " + String(currentWeatherCode));
        }
        http.end();

        // -----------------------------------------------------
        // 步骤 3：获取 CMA 官方灾害预警
        // -----------------------------------------------------
        String warnUrl = "https://" + String(QWEATHER_HOST) + "/v7/warning/now?location=" + locationID + "&lang=en";
        Serial.println("\n>>> [3/4] Requesting Warning Now...");
        http.begin(secureClient, warnUrl);
        http.addHeader("X-QW-Api-Key", QWEATHER_API_KEY);
        int warnCode = http.GET();
        String warnPayload = getDecompressedPayload(http);

        activeWarningCount = 0;

        if (warnCode == 200) {
            int searchPos = warnPayload.indexOf("\"warning\":[");
            if (searchPos >= 0) {
                int nextObj = warnPayload.indexOf("{", searchPos);
                int endArr = warnPayload.indexOf("]", searchPos);

                // 放宽到最大解析 15 个
                while (nextObj != -1 && nextObj < endArr && activeWarningCount < 15) {
                    int objEnd = warnPayload.indexOf("}", nextObj);
                    if (objEnd == -1) break;

                    String obj = warnPayload.substring(nextObj, objEnd + 1);

                    String color = parseJsonString(obj, "severityColor");
                    color.toLowerCase();
                    int lvl = 0;
                    if (color == "blue") lvl = 1;
                    else if (color == "yellow") lvl = 2;
                    else if (color == "orange") lvl = 3;
                    else if (color == "red" || color == "black") lvl = 4;

                    String typeStr = parseJsonString(obj, "type");
                    int typeCode = typeStr.toInt();

                    if (lvl > 0 && typeCode > 0) {
                        String newName = mapWarningTypeToName(typeCode);
                        bool isDuplicate = false;

                        // 同名去重逻辑：相同灾害类型出现多个级别，只保留最高级别
                        for (int i = 0; i < activeWarningCount; i++) {
                            if (activeWarnings[i].name == newName) {
                                isDuplicate = true;
                                if (lvl > activeWarnings[i].level) {
                                    activeWarnings[i].level = lvl;
                                    activeWarnings[i].iconCode = mapWarningTypeToIcon(typeCode);
                                }
                                break;
                            }
                        }
                        
                        if (!isDuplicate) {
                            activeWarnings[activeWarningCount].level = lvl;
                            activeWarnings[activeWarningCount].iconCode = mapWarningTypeToIcon(typeCode);
                            activeWarnings[activeWarningCount].name = newName;
                            activeWarningCount++;
                        }
                    }

                    nextObj = warnPayload.indexOf("{", objEnd);
                }

                // 稳定冒泡排序：高等级优先，同等级保持原始接收的时间优先顺序
                for (int i = 0; i < activeWarningCount - 1; i++) {
                    for (int j = i + 1; j < activeWarningCount; j++) {
                        if (activeWarnings[j].level > activeWarnings[i].level) {
                            WarningInfo temp = activeWarnings[i];
                            activeWarnings[i] = activeWarnings[j];
                            activeWarnings[j] = temp;
                        }
                    }
                }
                Serial.printf("--- CMA Warnings Found: %d\n", activeWarningCount);
                for(int i=0; i<activeWarningCount; i++){
                    Serial.printf("    [%d] Level: %d, Name: %s\n", i+1, activeWarnings[i].level, activeWarnings[i].name.c_str());
                }
            }
        }
        http.end();

        // -----------------------------------------------------
        // 步骤 4：获取 AQI 空气质量指数
        // -----------------------------------------------------
        if (currentLat != "" && currentLon != "") {
            String airUrl = "https://" + String(QWEATHER_HOST) + "/airquality/v1/current/" + currentLat + "/" + currentLon + "?lang=en";
            Serial.println("\n>>> [4/4] Requesting NEW Air API...");

            http.begin(secureClient, airUrl);
            http.addHeader("X-QW-Api-Key", QWEATHER_API_KEY);
            int airCode = http.GET();

            if (airCode == 200) {
                String airPayload = getDecompressedPayload(http);
                int idxPos = airPayload.indexOf("\"indexes\"");
                if (idxPos > 0) {
                    int aqiStart = airPayload.indexOf("\"aqi\":", idxPos);
                    if (aqiStart > 0) {
                        int valStart = airPayload.indexOf(":", aqiStart) + 1;
                        int valEnd = airPayload.indexOf(",", valStart);
                        if (valEnd == -1) valEnd = airPayload.indexOf("}", valStart);

                        currentAqi = airPayload.substring(valStart, valEnd);
                        currentAqi.replace("\"", "");
                        currentAqi.trim();
                        Serial.println("--- AQI Successfully Parsed: " + currentAqi);
                    }
                }
            } else {
                currentAqi = "N/A";
                Serial.printf("--- AQI Failed! Code: %d\n", airCode);
            }
            http.end();
        }
    }
}

float getDistance() {
    unsigned int dist_cm = sonar.ping_cm();
    if (dist_cm == 0) return 999.0;
    return (float)dist_cm;
}

void setLED(bool r, bool g, bool b) {
    uint32_t color = strip.Color(r? 255 : 0, g? 255 : 0, b? 255 : 0);
    for(int i = 0; i < strip.numPixels(); i++) {
        strip.setPixelColor(i, color);
    }
    strip.show();
}

void setCustomLEDColor(uint8_t r, uint8_t g, uint8_t b) {
    uint32_t color = strip.Color(r, g, b);
    for(int i = 0; i < strip.numPixels(); i++) {
        strip.setPixelColor(i, color);
    }
    strip.show();
}

void openDoor() {
    doorServo.write(SERVO_OPEN_SPEED);
    delay(250);
    doorServo.write(SERVO_STOP);
}

void closeDoor() {
    doorServo.write(SERVO_CLOSE_SPEED);
    delay(250);
    doorServo.write(SERVO_STOP);
}

void connectWiFi() {
    Serial.println();
    Serial.print("Connecting to WiFi: ");
    Serial.println(WIFI_SSID);
    displayMessage("Connecting...", WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WiFi connected!");
        displayMessage("WiFi Connected", WiFi.localIP().toString());
        delay(500);

        Serial.println("Syncing NTP Time & Weather...");
        configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
        syncWeather();
    } else {
        Serial.println("WiFi failed! Offline Mode.");
        displayMessage("WiFi Failed", "Offline Mode");
        delay(1000);
    }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    String msg = "";
    for (int i = 0; i < length; i++) {
        msg += (char)payload[i];
    }
    Serial.print(">>> MQTT Received from Cloud: ");
    Serial.println(msg);

    if (msg.indexOf("open") >= 0 || msg.indexOf("OPEN") >= 0) {
        Serial.println(">>> Remote Open Command Triggered! <<<");
        lastRecognizedUser = "Remote Admin";
        currentState = STATE_SUCCESS;
    }
    else if (msg.indexOf("\"cmd\":\"config\"") >= 0) {
        AI_MATCH_THRESHOLD = parseJsonValue(msg, "threshold", AI_MATCH_THRESHOLD);
        AUTO_CLOSE_TIME_SEC = (int)parseJsonValue(msg, "closeTime", AUTO_CLOSE_TIME_SEC);
        RECOGNITION_TIMEOUT_MS = (unsigned long)parseJsonValue(msg, "timeout", RECOGNITION_TIMEOUT_MS / 1000) * 1000;
        FACE_DETECTION_THRESHOLD = (int)parseJsonValue(msg, "frames", FACE_DETECTION_THRESHOLD);
        WAKEUP_DISTANCE_CM = parseJsonValue(msg, "wakeupDist", WAKEUP_DISTANCE_CM);

        String newLoc = parseJsonString(msg, "weatherLoc");
        if(newLoc.length() > 0 && newLoc != WEATHER_LOCATION) {
            WEATHER_LOCATION = newLoc;
            locationID = "";
            lastWeatherSyncTime = millis() - 300000;
        }

        int newBrightness = (int)parseJsonValue(msg, "brightness", LED_BRIGHTNESS);
        if (newBrightness != LED_BRIGHTNESS) {
            LED_BRIGHTNESS = newBrightness;
            strip.setBrightness(LED_BRIGHTNESS);
            if (currentState == STATE_SLEEP) strip.clear();
            strip.show();
        }

        LED_BASE_R = (int)parseJsonValue(msg, "r", LED_BASE_R);
        LED_BASE_G = (int)parseJsonValue(msg, "g", LED_BASE_G);
        LED_BASE_B = (int)parseJsonValue(msg, "b", LED_BASE_B);
    }
    else if (msg.indexOf("\"cmd\":\"auth\"") >= 0) {
        String targetUser = parseJsonString(msg, "user");
        int enable = (int)parseJsonValue(msg, "enable", 1);
        String userTag = "[" + targetUser + "]";

        if (enable == 0) {
            if (bannedUsers.indexOf(userTag) == -1) bannedUsers += userTag;
        } else {
            bannedUsers.replace(userTag, "");
        }
    }
}

// ==========================================
// 图像捕获与 AI 回调
// ==========================================
bool ei_camera_init(void) {
    if (is_initialised) return true;

    esp_err_t err = esp_camera_init(&camera_config);
    if (err != ESP_OK) return false;
    sensor_t * s = esp_camera_sensor_get();
    if (s->id.PID == OV3660_PID) {
      s->set_vflip(s, 1);
      s->set_brightness(s, 1);
      s->set_saturation(s, 0);
    }
    is_initialised = true;
    return true;
}

bool ei_camera_capture(uint32_t img_width, uint32_t img_height, uint8_t *out_buf) {
    bool do_resize = false;
    if (!is_initialised) return false;

    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) { esp_camera_fb_return(fb); }
    fb = esp_camera_fb_get();
    if (!fb) return false;

    bool converted = fmt2rgb888(fb->buf, fb->len, PIXFORMAT_JPEG, snapshot_buf);
    esp_camera_fb_return(fb);

    if(!converted) return false;
    if ((img_width != EI_CAMERA_RAW_FRAME_BUFFER_COLS) || (img_height != EI_CAMERA_RAW_FRAME_BUFFER_ROWS)) {
        do_resize = true;
    }
    if (do_resize) {
        ei::image::processing::crop_and_interpolate_rgb888(
            snapshot_buf, EI_CAMERA_RAW_FRAME_BUFFER_COLS, EI_CAMERA_RAW_FRAME_BUFFER_ROWS,
            out_buf, img_width, img_height);
    }
    return true;
}

static int ei_camera_get_data(size_t offset, size_t length, float *out_ptr) {
    size_t pixel_ix = offset * 3;
    size_t out_ptr_ix = 0;
    while (length != 0) {
        out_ptr[out_ptr_ix] = (snapshot_buf[pixel_ix + 2] << 16) + (snapshot_buf[pixel_ix + 1] << 8) + snapshot_buf[pixel_ix];
        out_ptr_ix++; pixel_ix+=3; length--;
    }
    return 0;
}

void setup() {
    disableCore0WDT();
    disableCore1WDT();
    disableLoopWDT();

    Serial.begin(115200);
    while (!Serial);

    Serial.println("\n--- V77 ---");

    doorServo.attach(SERVO_PIN, 500, 2400);
    doorServo.write(SERVO_STOP);

    strip.begin();
    strip.setBrightness(LED_BRIGHTNESS);
    strip.clear();
    strip.show();

    display.init();
    display.flipScreenVertically();

    connectWiFi();

    mqtt.setServer(MQTT_SERVER, MQTT_PORT);
    mqtt.setCallback(mqttCallback);

    display.clear();
    display.display();

    ei_camera_init();
    currentState = STATE_SLEEP;
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        if (!mqtt.connected()) {
            if (millis() - lastMqttReconnectAttempt > 5000) {
                lastMqttReconnectAttempt = millis();
                if (mqtt.connect(MQTT_CLIENT_ID)) mqtt.subscribe(MQTT_TOPIC);
            }
        } else {
            mqtt.loop();
        }
    }

    if (currentState == STATE_SLEEP && millis() - lastWeatherSyncTime > 300000) {
        syncWeather();
    }

    float dist = getDistance();

    switch (currentState) {
        case STATE_SLEEP:
            setLED(false, false, false);
            display.clear();
            display.display();

            if (dist < WAKEUP_DISTANCE_CM) {
                currentState = STATE_WAKEUP;
            }
            delay(200);
            break;

        case STATE_WAKEUP:
            setCustomLEDColor(255, 200, 120);
            drawScanningUI();
            recognizingStartTime = millis();
            faceDetectionCount = 0;
            delay(200);
            currentState = STATE_RECOGNIZING;
            break;

        case STATE_RECOGNIZING: {
            if (millis() - recognizingStartTime > RECOGNITION_TIMEOUT_MS) {
                currentState = STATE_FAILED;
                break;
            }
            if (ei_sleep(5) != EI_IMPULSE_OK) break;

            snapshot_buf = (uint8_t*)malloc(EI_CAMERA_RAW_FRAME_BUFFER_COLS * EI_CAMERA_RAW_FRAME_BUFFER_ROWS * EI_CAMERA_FRAME_BYTE_SIZE);
            if(snapshot_buf == nullptr) snapshot_buf = (uint8_t*)ps_malloc(EI_CAMERA_RAW_FRAME_BUFFER_COLS * EI_CAMERA_RAW_FRAME_BUFFER_ROWS * EI_CAMERA_FRAME_BYTE_SIZE);
            if(snapshot_buf == nullptr) { delay(100); break; }

            ei::signal_t signal;
            signal.total_length = EI_CLASSIFIER_INPUT_WIDTH * EI_CLASSIFIER_INPUT_HEIGHT;
            signal.get_data = &ei_camera_get_data;

            if (ei_camera_capture((size_t)EI_CLASSIFIER_INPUT_WIDTH, (size_t)EI_CLASSIFIER_INPUT_HEIGHT, snapshot_buf) == false) {
                free(snapshot_buf);
                break;
            }

            ei_impulse_result_t result = { 0 };
            EI_IMPULSE_ERROR err = run_classifier(&signal, &result, false);
            free(snapshot_buf);

            bool matched = false;
            String detectedUser = "";
            float maxConfidence = 0.0;

            if (err == EI_IMPULSE_OK) {
                for (uint16_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
                    String label = String(ei_classifier_inferencing_categories[i]);
                    float value = result.classification[i].value;
                    if (value >= AI_MATCH_THRESHOLD) {
                        label.toUpperCase();
                        if (label != "UNKNOWN" && label != "BACKGROUND") {
                            matched = true;
                            detectedUser = String(ei_classifier_inferencing_categories[i]); maxConfidence = value;
                        }
                    }
                }

                if (matched) {
                    String checkTag = "[" + detectedUser + "]";
                    if (bannedUsers.indexOf(checkTag) >= 0) {
                        if(mqtt.connected()) mqtt.publish(MQTT_TOPIC, ("{\"status\":\"failed\", \"msg\":\"未授权用户: " + detectedUser + "\"}").c_str());
                        setLED(true, false, false); drawDeniedUI("User Banned"); delay(1000); setCustomLEDColor(255, 200, 120); faceDetectionCount = 0;
                    } else {
                        faceDetectionCount++;
                        if (faceDetectionCount >= FACE_DETECTION_THRESHOLD) {
                            lastRecognizedUser = detectedUser;
                            if(mqtt.connected()) mqtt.publish(MQTT_TOPIC, ("{\"status\":\"passed\", \"user\":\"" + detectedUser + "\", \"confidence\":" + String(maxConfidence, 2) + "}").c_str());
                            currentState = STATE_SUCCESS;
                        } else {
                            drawVerifyingUI(detectedUser, faceDetectionCount, FACE_DETECTION_THRESHOLD);
                        }
                    }
                } else {
                    faceDetectionCount = 0;
                    drawScanningUI();
                }
            }
            break;
        }

        case STATE_SUCCESS: {
            openDoor();
            unsigned long doorOpenStartTime = millis();
            unsigned long lastUIRefresh = 0; // 强制 200ms OLED 刷新心跳
            int marquee_pos = 0, anim_val = 50, anim_dir = 25;

            while (true) {
                unsigned long currentMillis = millis();
                if(mqtt.connected()) mqtt.loop();

                unsigned long elapsed = currentMillis - doorOpenStartTime;
                int countdown = AUTO_CLOSE_TIME_SEC - (elapsed / 1000);

                if (countdown <= 0) {
                    closeDoor();
                    currentState = STATE_SLEEP;
                    break;
                }

                // 200ms 电竞级屏幕刷新锁
                if (currentMillis - lastUIRefresh >= 200) {
                    lastUIRefresh = currentMillis;

                    int currentWarningLevel = 0;
                    String currentWarningMsg = "";
                    int displayIcon = currentWeatherCode;
                    
                    // 【核心同步】：基于开门时间，实现精准的时间片轮播分配
                    if (activeWarningCount > 0) {
                        int displayLimit = activeWarningCount > 5 ? 5 : activeWarningCount;
                        
                        // 让第一个预警多显示1秒（即3秒），后续的都是2秒
                        unsigned long cycleTime = 3000 + (displayLimit - 1) * 2000;
                        unsigned long t = (currentMillis - doorOpenStartTime) % cycleTime;
                        
                        int warnIdx = 0;
                        if (t < 3000) {
                            warnIdx = 0; // 第一个独享前3秒
                        } else {
                            warnIdx = 1 + (t - 3000) / 2000; // 后续每2秒切一次
                        }
                        
                        if (warnIdx >= displayLimit) warnIdx = displayLimit - 1; // 边界保护
                        
                        currentWarningLevel = activeWarnings[warnIdx].level;
                        currentWarningMsg = activeWarnings[warnIdx].name;
                        if (activeWarnings[warnIdx].iconCode != 0) {
                            displayIcon = activeWarnings[warnIdx].iconCode;
                        }
                    }

                    // 闪烁状态：严格保证 200ms 和 400ms 的翻转频率
                    bool currentBlinkState = true;
                    if (currentWarningLevel == 3) currentBlinkState = (currentMillis % 800) < 400; // 橙警 400ms翻转一次
                    else if (currentWarningLevel == 4) currentBlinkState = (currentMillis % 400) < 200; // 红警 200ms翻转一次

                    struct tm timeinfo;
                    bool timeValid = getLocalTime(&timeinfo, 100);
                    String greeting = "Welcome,";
                    if (timeValid) {
                        if (timeinfo.tm_hour >= 5 && timeinfo.tm_hour < 12) greeting = "Good Morning,";
                        else if (timeinfo.tm_hour >= 12 && timeinfo.tm_hour < 18) greeting = "Good Afternoon,";
                        else greeting = "Good Evening,";
                    }

                    display.clear();
                    display.setTextAlignment(TEXT_ALIGN_LEFT);
                    display.setFont(ArialMT_Plain_10);

                    // UI排版与闪烁机制（橙色底条闪烁且防切断）
                    if (currentWarningLevel > 0) {
                        int bx = 6, by = 6;
                        int textW = display.getStringWidth(currentWarningMsg);

                        if (currentWarningLevel == 4) {
                            if (currentBlinkState) {
                                display.setColor(WHITE);
                                display.fillRect(0, 0, 18 + textW, 13);
                                display.setColor(BLACK);
                            } else {
                                display.setColor(WHITE);
                            }
                            display.fillRect(bx-3, by-5, 7, 11);
                            display.fillRect(bx-5, by-3, 11, 7);
                            display.setColor(currentBlinkState ? WHITE : BLACK); 
                            display.drawLine(bx, by-2, bx, by+1); display.setPixel(bx, by+3); 
                            display.setColor(currentBlinkState ? BLACK : WHITE);
                            
                            display.drawString(16, 0, currentWarningMsg);
                            display.setColor(WHITE);
                        } 
                        else {
                            display.setColor(WHITE);
                            if (currentWarningLevel == 1) {
                                display.drawCircle(bx, by, 5);
                                display.drawLine(bx, by-2, bx, by+1); display.setPixel(bx, by+3);
                            }
                            else if (currentWarningLevel == 2) {
                                display.drawLine(bx, by-5, bx-5, by+4);
                                display.drawLine(bx, by-5, bx+5, by+4); display.drawLine(bx-5, by+4, bx+5, by+4);
                                display.drawLine(bx, by-1, bx, by+1); display.setPixel(bx, by+3);
                            }
                            else if (currentWarningLevel == 3) {
                                display.drawLine(bx, by-5, bx-5, by);
                                display.drawLine(bx-5, by, bx, by+5); display.drawLine(bx, by+5, bx+5, by); display.drawLine(bx+5, by, bx, by-5);
                                display.drawLine(bx, by-2, bx, by+1); display.setPixel(bx, by+3);
                                
                                // 橙色预警特有：不影响字体排版，直接在底部画 2 像素宽闪烁下划线
                                if (currentBlinkState) {
                                    display.fillRect(0, 11, 17 + textW, 2);
                                }
                            }
                            // 蓝、黄、橙警：文字常驻显示，Y轴恢复0防止刀切
                            display.drawString(16, 0, currentWarningMsg);
                        }
                    } else {
                        display.drawString(0, 0, greeting);
                    }

                    display.setTextAlignment(TEXT_ALIGN_RIGHT);
                    display.drawString(128, 0, currentTemp);

                    int tempW = display.getStringWidth(currentTemp);
                    int wx = 128 - tempW - 10;
                    int wy = 5;

                    switch (displayIcon) {
                        case 0: // ☀️ 晴朗
                            display.drawCircle(wx, wy, 3);
                            display.drawLine(wx, wy-5, wx, wy-7); display.drawLine(wx, wy+5, wx, wy+7);
                            display.drawLine(wx-5, wy, wx-7, wy); display.drawLine(wx+5, wy, wx+7, wy);
                            break;
                        case 1: // ☁️ 多云
                            display.fillCircle(wx-4, wy+1, 3);
                            display.fillCircle(wx, wy-2, 4); display.fillCircle(wx+5, wy+1, 3); display.fillRect(wx-4, wy, 10, 5);
                            break;
                        case 2: // 🌧️ 雨
                            display.drawCircle(wx-4, wy, 3);
                            display.drawCircle(wx, wy-3, 4); display.drawCircle(wx+4, wy, 3);
                            display.drawLine(wx-3, wy+4, wx-5, wy+7); display.drawLine(wx, wy+4, wx-2, wy+7); display.drawLine(wx+3, wy+4, wx+1, wy+7);
                            break;
                        case 3: // ⛈️ 暴雨
                            display.fillCircle(wx-3, wy-2, 2);
                            display.fillCircle(wx, wy-3, 3); display.fillCircle(wx+3, wy-2, 2); display.fillRect(wx-3, wy-2, 7, 3);
                            display.drawLine(wx-4, wy+2, wx-5, wy+5); display.drawLine(wx-1, wy+2, wx-2, wy+5);
                            display.drawLine(wx+2, wy+2, wx+1, wy+5); display.drawLine(wx+5, wy+2, wx+4, wy+5);
                            break;
                        case 4: // ❄️ 暴雪
                            display.drawLine(wx, wy-4, wx, wy+4);
                            display.drawLine(wx-1, wy-4, wx-1, wy+4);
                            display.drawLine(wx-3, wy-3, wx+3, wy+3); display.drawLine(wx-3, wy-2, wx+2, wy+3);
                            display.drawLine(wx-3, wy+3, wx+3, wy-3); display.drawLine(wx-3, wy+2, wx+2, wy-3);
                            break;
                        case 5: // 🥶 寒潮
                            display.drawLine(wx-4, wy-4, wx+4, wy-4);
                            display.drawLine(wx-4, wy-4, wx-4, wy); display.drawLine(wx+4, wy-4, wx+4, wy);
                            display.drawLine(wx-6, wy, wx+6, wy); display.drawLine(wx-6, wy, wx, wy+5); display.drawLine(wx+6, wy, wx, wy+5);
                            display.drawCircle(wx, wy-2, 1);
                            break;
                        case 6: // 💨 大风
                            display.drawLine(wx-3, wy-4, wx-3, wy+5);
                            display.drawLine(wx-3, wy-4, wx+4, wy-1); display.drawLine(wx-3, wy+2, wx+4, wy-1);
                            break;
                        case 7: // 🌪️ 沙尘暴
                            display.drawLine(wx+2, wy-4, wx-1, wy-4);
                            display.drawLine(wx-1, wy-4, wx-2, wy-3); display.drawLine(wx-2, wy-3, wx-2, wy-2); display.drawLine(wx-2, wy-2, wx+1, wy); display.drawLine(wx+1, wy, wx+2, wy+1); display.drawLine(wx+2, wy+1, wx+2, wy+3);
                            display.drawLine(wx+2, wy+3, wx-1, wy+3);
                            display.drawLine(wx-4, wy, wx+4, wy); display.drawLine(wx+4, wy, wx+2, wy-2); display.drawLine(wx+4, wy, wx+2, wy+2);
                            break;
                        case 8: // 🌡️ 高温
                            display.drawLine(wx, wy-5, wx-5, wy);
                            display.drawLine(wx, wy-5, wx+5, wy); display.drawLine(wx-5, wy, wx-5, wy+5); display.drawLine(wx+5, wy, wx+5, wy+5); display.drawLine(wx-5, wy+5, wx+5, wy+5);
                            display.drawCircle(wx, wy+2, 1);
                            display.drawLine(wx, wy-2, wx, wy+1);
                            break;
                        case 9: // 🏜️ 干旱
                            display.drawLine(wx-5, wy+4, wx+5, wy+4);
                            for(int i=-4; i<=2; i+=3) { display.drawLine(i+wx, wy-4, i+2+wx, wy-1); display.drawLine(i+2+wx, wy-1, i+wx, wy+2); display.drawLine(i+wx, wy+2, i+1+wx, wy+4);
                            }
                            break;
                        case 10: // ⚡ 雷电
                            display.drawLine(wx+2, wy-5, wx-3, wy+1);
                            display.drawLine(wx+3, wy-5, wx-2, wy+1);
                            display.drawLine(wx-3, wy+1, wx+1, wy+1); display.drawLine(wx-2, wy+1, wx+2, wy+1);
                            display.drawLine(wx+2, wy+1, wx-2, wy+6); display.drawLine(wx+1, wy+1, wx-3, wy+6);
                            break;
                        case 11: // 🧊 冰雹
                            display.drawLine(wx, wy-4, wx-3, wy-1);
                            display.drawLine(wx, wy-4, wx+3, wy-1);
                            display.drawLine(wx-3, wy-1, wx, wy+5); display.drawLine(wx+3, wy-1, wx, wy+5);
                            display.drawLine(wx, wy-4, wx, wy+5); display.drawLine(wx-3, wy-1, wx+3, wy-1);
                            break;
                        case 12: // 🌀 台风
                            display.drawCircle(wx, wy, 2);
                            display.setPixel(wx-3, wy-1); display.setPixel(wx-4, wy-2); display.setPixel(wx-3, wy-3);
                            display.setPixel(wx+3, wy+1); display.setPixel(wx+4, wy+2); display.setPixel(wx+3, wy+3);
                            break;
                        case 13: // 霜冻
                            display.drawLine(wx-5, wy-4, wx-5, wy+4);
                            display.drawLine(wx+5, wy-4, wx+5, wy+4); display.drawLine(wx-5, wy+4, wx+5, wy+4);
                            display.drawLine(wx, wy-2, wx, wy+2); display.drawLine(wx-2, wy-1, wx+2, wy+1); display.drawLine(wx-2, wy+1, wx+2, wy-1);
                            break;
                        case 14: // 大雾
                            display.fillRect(wx-5, wy-3, 11, 2);
                            display.fillRect(wx-5, wy, 11, 2); display.fillRect(wx-5, wy+3, 11, 2);
                            break;
                        case 15: // 道路结冰
                            display.fillRect(wx-3, wy-5, 7, 4);
                            display.setPixel(wx-2, wy-1); display.setPixel(wx+2, wy-1);
                            display.drawLine(wx-4, wy+1, wx-2, wy+3); display.drawLine(wx-2, wy+3, wx-4, wy+5);
                            display.drawLine(wx+1, wy+1, wx+3, wy+3); display.drawLine(wx+3, wy+3, wx+1, wy+5);
                            break;
                        case 16: // 霾
                            display.drawCircle(wx-3, wy, 2);
                            display.drawCircle(wx+3, wy, 2); display.setPixel(wx, wy);
                            break;
                        case 17: // 雷雨大风
                            display.drawLine(wx-4, wy-5, wx-4, wy+3);
                            display.drawLine(wx-4, wy-5, wx+1, wy-3); display.drawLine(wx-4, wy-1, wx+1, wy-3);
                            display.drawLine(wx+2, wy-1, wx, wy+2); display.drawLine(wx, wy+2, wx+3, wy+2); display.drawLine(wx+3, wy+2, wx+1, wy+5);
                            break;
                        case 18: // 重污染天气
                            display.drawCircle(wx+1, wy-2, 3);
                            display.drawLine(wx-1, wy, wx-3, wy+2);
                            display.fillRect(wx-4, wy+2, 4, 3);
                            display.drawLine(wx-4, wy+2, wx+2, wy+1); display.drawLine(wx-4, wy+5, wx+2, wy+3);
                            break;
                    }

                    display.setTextAlignment(TEXT_ALIGN_CENTER);
                    display.setFont(ArialMT_Plain_16);
                    display.drawString(64, 20, lastRecognizedUser);
                    display.drawString(65, 20, lastRecognizedUser);

                    display.setFont(ArialMT_Plain_10);
                    display.setTextAlignment(TEXT_ALIGN_LEFT);

                    String bottomStr = "";
                    if (timeValid) {
                        char timeBuff[10];
                        strftime(timeBuff, sizeof(timeBuff), "%H:%M", &timeinfo);
                        bottomStr = String(timeBuff);
                    } else {
                        bottomStr = "--:--";
                    }

                    if (currentAqi != "--") {
                        bottomStr += "  AQI:" + currentAqi;
                    }
                    display.drawString(0, 42, bottomStr);

                    display.setTextAlignment(TEXT_ALIGN_RIGHT);
                    display.drawString(128, 42, "Lock: " + String(countdown) + "s");

                    int progress = (countdown * 100) / AUTO_CLOSE_TIME_SEC;
                    display.drawProgressBar(0, 56, 128, 6, progress);

                    display.display();
                }

                // --------- 灯带独立动画，每 80ms 执行一次 ---------
                strip.clear();
                for(int i = 0; i < 4; i++) {
                    int pos = (marquee_pos - i + strip.numPixels()) % strip.numPixels();
                    int brightness = anim_val - (i * 30);
                    if(brightness < 0) brightness = 0;

                    float ratio = brightness / 255.0;
                    int r = LED_BASE_R * ratio;
                    int g = LED_BASE_G * ratio;
                    int b = LED_BASE_B * ratio;
                    strip.setPixelColor(pos, strip.Color(r, g, b));
                }
                strip.show();

                marquee_pos++;
                if (marquee_pos >= strip.numPixels()) {
                    marquee_pos = 0;
                    anim_val += anim_dir;
                    if (anim_val >= 255) { anim_val = 255; anim_dir = -25; }
                    else if (anim_val <= 50) { anim_val = 50; anim_dir = 25; }
                }
                delay(80);
            }
            break;
        }

        case STATE_FAILED:
            if(mqtt.connected()) mqtt.publish(MQTT_TOPIC, "{\"status\":\"failed\", \"msg\":\"timeout or unrecognized user\"}");
            setLED(true, false, false);
            drawDeniedUI("Timeout");
            delay(3000);
            currentState = STATE_SLEEP;
            break;
    }
}