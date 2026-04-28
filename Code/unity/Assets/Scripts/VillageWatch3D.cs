using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Networking;
using UnityEngine.UI;

public sealed class VillageWatch3D : MonoBehaviour
{
    [Header("Backend")]
    public string serviceBaseUrl = "http://127.0.0.1:8000";

    [Header("Movement")]
    public float playerSpeed = 7.0f;
    public float autoTickInterval = 1.0f;

    [Header("Camera")]
    public Vector3 cameraFollowOffset = new Vector3(0.0f, 6.6f, -8.2f);
    public Vector3 cameraLookOffset = new Vector3(0.0f, 1.15f, 1.3f);
    public float cameraFollowSmoothTime = 0.12f;
    public float cameraDistance = 10.5f;
    public float mouseSensitivity = 2.2f;
    public float minCameraPitch = 18.0f;
    public float maxCameraPitch = 68.0f;

    private const string PlayerId = "player_001";
    private const string PlayerActorId = "player";
    private const float InteractionDistance = 2.2f;

    private readonly Dictionary<string, AreaDef> areas = new Dictionary<string, AreaDef>();
    private readonly Dictionary<string, string> areaByLocation = new Dictionary<string, string>();
    private readonly Dictionary<string, string> locationByArea = new Dictionary<string, string>();
    private readonly Dictionary<string, ActorView> actors = new Dictionary<string, ActorView>();
    private readonly Dictionary<string, Dictionary<string, Vector3>> npcAreaPositions = new Dictionary<string, Dictionary<string, Vector3>>();
    private readonly List<HotspotView> hotspotViews = new List<HotspotView>();
    private readonly List<GameObject> spawnedAreaObjects = new List<GameObject>();
    private readonly List<GameObject> dynamicWorldObjects = new List<GameObject>();

    private NpcSocialRpgClient api;
    private Camera worldCamera;
    private Transform worldRoot;
    private Transform actorRoot;
    private Transform hotspotRoot;
    private Transform propRoot;
    private Transform dynamicRoot;
    private GameObject backdrop;
    private Material backdropMaterial;
    private Material groundMaterial;
    private GameObject playerObject;
    private Vector3 cameraVelocity;
    private bool cursorLookEnabled;
    private float cameraYaw;
    private float cameraPitch = 38.0f;

    private Text tickLabel;
    private Text statusLabel;
    private Text selectedLabel;
    private Text dialogueLog;
    private Text thoughtLog;
    private Text taskLog;
    private Text eventLog;
    private Text eventDetailLog;
    private InputField speechInput;
    private Button autoTickButton;
    private InputField autoTickInput;

    private int currentTick;
    private string currentAreaId = "village_entrance";
    private string selectedNpcId = "";
    private string targetNpcId = "";
    private HotspotView targetHotspot;
    private bool pendingPlanThenExecute;
    private bool tickRequestInFlight;
    private bool autoTickEnabled;
    private float autoTickTimer;
    private string lastEconomySummary = "";

    private void Awake()
    {
        GameObject bakedPreview = GameObject.Find("Baked Unity 3D Migration Preview");
        if (bakedPreview != null)
        {
            bakedPreview.SetActive(false);
        }

        BuildDefinitions();
        api = new NpcSocialRpgClient(this, serviceBaseUrl);
        BuildWorld();
        BuildUi();
        SwitchArea("village_entrance", "初始展示村庄入口。", null);
    }

    private void Start()
    {
        SetStatus("正在读取后端状态。");
        RefreshBackendState();
    }

    private void Update()
    {
        HandleCursorToggle();
        UpdateMouseLook();
        MovePlayer();
        UpdateInteractionState();
        UpdateAutoTick();
        HandleHotkeys();
    }

    private void LateUpdate()
    {
        if (worldCamera == null)
        {
            return;
        }

        UpdateCameraFollow(false);

        foreach (ActorView actor in actors.Values)
        {
            actor.FaceCamera(worldCamera.transform.rotation);
        }

        foreach (HotspotView hotspot in hotspotViews)
        {
            hotspot.FaceCamera(worldCamera.transform.rotation);
        }

        foreach (GameObject item in dynamicWorldObjects)
        {
            if (item == null)
            {
                continue;
            }
            TextMesh mesh = item.GetComponentInChildren<TextMesh>();
            if (mesh != null)
            {
                mesh.transform.rotation = worldCamera.transform.rotation;
            }
        }
    }

    private void BuildDefinitions()
    {
        AddArea("village_entrance", "村庄入口", "城门、哨塔和水渠在这里，适合展示安保与来客检查。", "Backgrounds/village_entrance", new Color(0.29f, 0.43f, 0.30f));
        AddArea("village_square", "村庄广场", "喷泉和公告厅是公共交流中心，适合观察人群流动。", "Backgrounds/village_square", new Color(0.31f, 0.40f, 0.34f));
        AddArea("village_market", "村庄集市", "摊位和货箱对应交易、短缺与偷窃等事件。", "Backgrounds/village_market", new Color(0.40f, 0.34f, 0.25f));
        AddArea("hunting_forest", "狩猎森林", "猎人营地和兽道连接巡逻、狩猎与怪物事件。", "Backgrounds/hunting_forest", new Color(0.18f, 0.38f, 0.24f));
        AddArea("village_rest_area", "村庄休息处", "营火、小屋与瀑布平台适合休整和连续对话展示。", "Backgrounds/village_rest_area", new Color(0.27f, 0.35f, 0.30f));

        areaByLocation["village_gate"] = "village_entrance";
        areaByLocation["village_square"] = "village_square";
        areaByLocation["market"] = "village_market";
        areaByLocation["forest_edge"] = "hunting_forest";
        areaByLocation["inn"] = "village_rest_area";

        locationByArea["village_entrance"] = "village_gate";
        locationByArea["village_square"] = "village_square";
        locationByArea["village_market"] = "market";
        locationByArea["hunting_forest"] = "forest_edge";
        locationByArea["village_rest_area"] = "inn";

        AddNpcPositions("npc_guard_001", new Dictionary<string, Vector3>
        {
            {"village_entrance", MapPoint(720, 640)},
            {"village_square", MapPoint(1030, 645)},
            {"village_market", MapPoint(1030, 720)}
        });
        AddNpcPositions("npc_merchant_001", new Dictionary<string, Vector3>
        {
            {"village_market", MapPoint(810, 650)},
            {"village_square", MapPoint(980, 660)},
            {"village_rest_area", MapPoint(1020, 710)}
        });
        AddNpcPositions("npc_hunter_001", new Dictionary<string, Vector3>
        {
            {"hunting_forest", MapPoint(900, 610)},
            {"village_market", MapPoint(1080, 710)},
            {"village_rest_area", MapPoint(980, 760)}
        });
        AddNpcPositions("npc_farmer_001", new Dictionary<string, Vector3>
        {
            {"village_square", MapPoint(520, 700)},
            {"village_market", MapPoint(480, 800)}
        });
        AddNpcPositions("npc_blacksmith_001", new Dictionary<string, Vector3>
        {
            {"village_square", MapPoint(610, 705)},
            {"village_entrance", MapPoint(880, 660)}
        });
        AddNpcPositions("npc_physician_001", new Dictionary<string, Vector3>
        {
            {"village_square", MapPoint(700, 710)},
            {"village_rest_area", MapPoint(820, 735)}
        });
        AddNpcPositions("npc_village_chief_001", new Dictionary<string, Vector3>
        {
            {"village_square", MapPoint(790, 690)},
            {"village_entrance", MapPoint(840, 620)},
            {"village_market", MapPoint(910, 690)}
        });

        AddHotspot("village_entrance", "进入广场", "transition", "village_square", "", MapPoint(580, 470), "穿过城门后进入广场。");
        AddHotspot("village_entrance", "守卫哨塔", "focus_npc", "", "npc_guard_001", MapPoint(910, 310), "守卫在这里观察来客与出入口。");
        AddHotspot("village_entrance", "水渠磨坊", "inspect", "", "", MapPoint(1080, 470), "这里可承接供水、民生或事故类事件。");
        AddHotspot("village_entrance", "村外小路", "inspect", "", "", MapPoint(180, 860), "这里通向村外，可作为后续地图扩展入口。");

        AddHotspot("village_square", "回到入口", "transition", "village_entrance", "", MapPoint(640, 455), "从这里可以回到村庄入口。");
        AddHotspot("village_square", "前往集市", "transition", "village_market", "", MapPoint(1020, 520), "沿街巷前往商铺最密集的区域。");
        AddHotspot("village_square", "前往休息处", "transition", "village_rest_area", "", MapPoint(320, 660), "沿树荫与长椅区前往休息处。");
        AddHotspot("village_square", "中央喷泉", "inspect", "", "", MapPoint(650, 575), "喷泉适合展示闲聊、传闻与公共聚集。");
        AddHotspot("village_square", "公告大厅", "inspect", "", "", MapPoint(780, 260), "这里可承接任务发布与公共事件说明。");

        AddHotspot("village_market", "商人摊位", "focus_npc", "", "npc_merchant_001", MapPoint(760, 470), "商人在这里交易，也适合展示市场传闻。");
        AddHotspot("village_market", "补给货箱", "inspect", "", "", MapPoint(530, 840), "这里适合展示资源短缺、偷窃与物资调度。");
        AddHotspot("village_market", "回到广场", "transition", "village_square", "", MapPoint(640, 930), "从集市下方回到广场。");
        AddHotspot("village_market", "前往森林", "transition", "hunting_forest", "", MapPoint(1060, 260), "从集市旁林道进入狩猎森林。");

        AddHotspot("hunting_forest", "猎人营地", "focus_npc", "", "npc_hunter_001", MapPoint(860, 390), "猎人会在这里巡查、休整和讨论林地情况。");
        AddHotspot("hunting_forest", "林间兽道", "inspect", "", "", MapPoint(700, 720), "兽道可承接怪物出现、追踪与调查。");
        AddHotspot("hunting_forest", "去休息处", "transition", "village_rest_area", "", MapPoint(250, 520), "沿营火旁小路返回休息处。");
        AddHotspot("hunting_forest", "回到集市", "transition", "village_market", "", MapPoint(1110, 520), "沿林边棚屋可回到集市。");

        AddHotspot("village_rest_area", "休息小屋", "rest", "", "", MapPoint(1030, 360), "这里适合承接休息、恢复与夜间驻留。");
        AddHotspot("village_rest_area", "营火区", "rest", "", "", MapPoint(690, 760), "营火适合慢节奏对话、总结与队伍集合。");
        AddHotspot("village_rest_area", "回到广场", "transition", "village_square", "", MapPoint(250, 590), "从木桌区可快速回到广场。");
        AddHotspot("village_rest_area", "进入森林", "transition", "hunting_forest", "", MapPoint(860, 180), "从瀑布旁路口进入森林。");
    }

    private void BuildWorld()
    {
        worldRoot = new GameObject("GeneratedWorld").transform;
        actorRoot = NewChild(worldRoot, "Actors");
        hotspotRoot = NewChild(worldRoot, "Hotspots");
        propRoot = NewChild(worldRoot, "AreaProps");
        dynamicRoot = NewChild(worldRoot, "DynamicWorld");

        worldCamera = new GameObject("Main Camera").AddComponent<Camera>();
        worldCamera.tag = "MainCamera";
        worldCamera.orthographic = false;
        worldCamera.fieldOfView = 54.0f;
        worldCamera.nearClipPlane = 0.08f;
        worldCamera.farClipPlane = 120.0f;
        worldCamera.clearFlags = CameraClearFlags.SolidColor;
        worldCamera.backgroundColor = new Color(0.32f, 0.43f, 0.50f);
        cameraYaw = 0.0f;
        cameraPitch = 38.0f;
        SetCursorLook(false);

        Light sun = new GameObject("Sun").AddComponent<Light>();
        sun.type = LightType.Directional;
        sun.intensity = 1.25f;
        sun.transform.rotation = Quaternion.Euler(52, -34, 0);

        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.52f, 0.57f, 0.60f);
        RenderSettings.ambientEquatorColor = new Color(0.38f, 0.34f, 0.29f);
        RenderSettings.ambientGroundColor = new Color(0.20f, 0.18f, 0.15f);

        GameObject ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "Village Ground";
        ground.transform.SetParent(worldRoot, false);
        ground.transform.localScale = new Vector3(2.6f, 1, 1.9f);
        groundMaterial = NewStandardMaterial(new Color(0.29f, 0.40f, 0.29f), 0.25f, 0.15f);
        ground.GetComponent<Renderer>().sharedMaterial = groundMaterial;

        backdrop = GameObject.CreatePrimitive(PrimitiveType.Quad);
        backdrop.name = "Area Backdrop";
        backdrop.transform.SetParent(worldRoot, false);
        backdrop.transform.position = new Vector3(0, 5.3f, 8.6f);
        backdrop.transform.rotation = Quaternion.Euler(0, 180, 0);
        backdrop.transform.localScale = new Vector3(21.5f, 12.1f, 1);
        backdropMaterial = NewUnlitMaterial(Color.white);
        backdrop.GetComponent<Renderer>().sharedMaterial = backdropMaterial;

        playerObject = CreateActorObject(PlayerActorId, "Player", new Color(0.18f, 0.42f, 0.95f));
        playerObject.transform.position = MapPoint(460, 780);
        actors[PlayerActorId] = new ActorView(PlayerActorId, "Player", "player", "village_entrance", playerObject);
        UpdateCameraFollow(true);
    }

    private void BuildUi()
    {
        Canvas canvas = new GameObject("Unity3D HUD").AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        CanvasScaler scaler = canvas.gameObject.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        canvas.gameObject.AddComponent<GraphicRaycaster>();

        if (FindObjectOfType<EventSystem>() == null)
        {
            GameObject eventSystem = new GameObject("EventSystem");
            eventSystem.AddComponent<EventSystem>();
            eventSystem.AddComponent<StandaloneInputModule>();
        }

        Font font = CreateReadableFont();
        RectTransform sidebar = CreatePanel(canvas.transform, "Sidebar", new Vector2(1, 0), new Vector2(1, 1), new Vector2(-548, 16), new Vector2(-16, -16), new Color(0.08f, 0.095f, 0.11f, 0.96f));
        VerticalLayoutGroup layout = sidebar.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.padding = new RectOffset(14, 14, 14, 14);
        layout.spacing = 8;
        layout.childControlHeight = true;
        layout.childForceExpandHeight = false;
        layout.childControlWidth = true;
        layout.childForceExpandWidth = true;

        RectTransform titlePanel = CreateGroup(sidebar, "TitlePanel", 86);
        tickLabel = AddText(titlePanel, "Tick 0", 18, new Color(0.98f, 0.93f, 0.70f), font, TextAnchor.UpperRight);
        tickLabel.rectTransform.anchorMin = new Vector2(0.72f, 0);
        tickLabel.rectTransform.anchorMax = new Vector2(1, 1);
        tickLabel.rectTransform.offsetMin = Vector2.zero;
        tickLabel.rectTransform.offsetMax = Vector2.zero;
        Text title = AddText(titlePanel, "Village Watch 3D", 28, new Color(0.98f, 0.96f, 0.88f), font, TextAnchor.UpperLeft);
        title.rectTransform.anchorMax = new Vector2(0.72f, 1);
        Text subtitle = AddText(titlePanel, "Unity 3D runtime migration", 15, new Color(0.72f, 0.80f, 0.76f), font, TextAnchor.LowerLeft);
        subtitle.rectTransform.anchorMax = new Vector2(0.90f, 0.52f);

        statusLabel = AddBoxText(sidebar, "Status", 58, "状态：启动中...", 16, font);
        selectedLabel = AddBoxText(sidebar, "Selected", 48, "附近 NPC：无", 16, font);
        dialogueLog = AddBoxText(sidebar, "Dialogue", 144, "对话记录会显示在这里。", 15, font);
        speechInput = AddInput(sidebar, "SpeechInput", "对附近 NPC 说些什么...", font, 44);

        RectTransform buttonRow = CreateGroup(sidebar, "ButtonRow", 42);
        HorizontalLayoutGroup buttonLayout = buttonRow.gameObject.AddComponent<HorizontalLayoutGroup>();
        buttonLayout.spacing = 6;
        buttonLayout.childForceExpandWidth = true;
        AddButton(buttonRow, "对话 / E", font, OnSubmitPressed);
        AddButton(buttonRow, "可疑 / O", font, OnSuspiciousEventPressed);
        AddButton(buttonRow, "规划 / P", font, OnPlanExecutePressed);
        AddButton(buttonRow, "重置 / R", font, OnResetPressed);

        RectTransform tickRow = CreateGroup(sidebar, "TickRow", 42);
        HorizontalLayoutGroup tickLayout = tickRow.gameObject.AddComponent<HorizontalLayoutGroup>();
        tickLayout.spacing = 6;
        tickLayout.childForceExpandWidth = true;
        AddButton(tickRow, "推进 Tick / T", font, OnAdvanceTickPressed);
        autoTickButton = AddButton(tickRow, "自动推进：关", font, OnAutoTickPressed);
        autoTickInput = AddInput(tickRow, "AutoTickInput", "1.0", font, 42);
        autoTickInput.text = autoTickInterval.ToString("0.0", CultureInfo.InvariantCulture);

        RectTransform eventRow = CreateGroup(sidebar, "EventRow", 42);
        HorizontalLayoutGroup eventLayout = eventRow.gameObject.AddComponent<HorizontalLayoutGroup>();
        eventLayout.spacing = 6;
        eventLayout.childForceExpandWidth = true;
        AddButton(eventRow, "怪物", font, OnMonsterEventPressed);
        AddButton(eventRow, "短缺", font, OnResourceEventPressed);
        AddButton(eventRow, "偷窃", font, OnTheftEventPressed);

        thoughtLog = AddBoxText(sidebar, "ThoughtLog", 128, "思考与规划结果会显示在这里。", 14, font);
        taskLog = AddBoxText(sidebar, "TaskLog", 142, "任务执行结果会显示在这里。", 14, font);
        eventLog = AddBoxText(sidebar, "EventLog", 110, "世界事件记录会显示在这里。", 14, font);
        eventDetailLog = AddBoxText(sidebar, "EventDetailLog", 138, "建筑、热点、资源和经济状态会显示在这里。", 14, font);
    }

    private void RefreshBackendState()
    {
        api.Get("/npcs", OnNpcListReceived, message => OnRequestFailed("NPC 列表", message));
        api.Get("/world/resources?location_id=" + CurrentLocationId(), OnWorldResourcesReceived, message => OnRequestFailed("World Resources", message));
        api.Get("/world/entities?location_id=" + CurrentLocationId(), OnWorldEntitiesReceived, message => OnRequestFailed("World Entities", message));
        api.Get("/events?limit=50", OnEventLogReceived, message => OnRequestFailed("事件日志", message));
        RefreshEconomyState();
        if (!string.IsNullOrEmpty(selectedNpcId))
        {
            RequestDialogueHistory(selectedNpcId);
            RequestInventory(selectedNpcId);
        }
    }

    private void RefreshEconomyState()
    {
        api.Get("/village/warehouse", obj => UpdateEconomy("warehouse", obj), message => OnRequestFailed("共享仓库", message));
        api.Get("/village/production-orders?include_completed=false", obj => UpdateEconomy("orders", obj), message => OnRequestFailed("生产订单", message));
        api.Get("/village/warehouse/transactions?limit=8", obj => UpdateEconomy("transactions", obj), message => OnRequestFailed("仓库流水", message));
    }

    private readonly Dictionary<string, object> economy = new Dictionary<string, object>();

    private void UpdateEconomy(string key, object value)
    {
        economy[key] = value;
        string summary = FormatEconomySummary();
        if (!string.IsNullOrEmpty(summary) && summary != lastEconomySummary)
        {
            lastEconomySummary = summary;
            AppendEventDetail(summary);
        }
    }

    private void SwitchArea(string areaId, string statusText, Vector3? spawnPosition)
    {
        if (!areas.ContainsKey(areaId))
        {
            return;
        }

        currentAreaId = areaId;
        AreaDef area = areas[areaId];
        currentAreaId = areaId;
        Texture2D backdropTexture = Resources.Load<Texture2D>(area.backgroundResource);
        if (backdropTexture != null)
        {
            backdropTexture.filterMode = FilterMode.Trilinear;
            backdropTexture.anisoLevel = 8;
            backdropMaterial.mainTexture = backdropTexture;
        }

        groundMaterial.color = area.groundColor;
        playerObject.transform.position = spawnPosition ?? DefaultSpawnForArea(areaId);
        UpdateCameraFollow(true);
        selectedNpcId = "";
        targetNpcId = "";
        targetHotspot = null;
        RebuildAreaProps(areaId);
        RebuildHotspots(areaId);
        UpdateActorVisibility();
        SetStatus(string.IsNullOrEmpty(statusText) ? area.displayName + "：" + area.subtitle : statusText);
        AppendEventDetail(area.displayName + "\n" + area.subtitle);
        api.Get("/world/resources?location_id=" + CurrentLocationId(), OnWorldResourcesReceived, message => OnRequestFailed("World Resources", message));
        api.Get("/world/entities?location_id=" + CurrentLocationId(), OnWorldEntitiesReceived, message => OnRequestFailed("World Entities", message));
        UpdateSelectedLabel();
    }

    private void RebuildAreaProps(string areaId)
    {
        foreach (GameObject item in spawnedAreaObjects)
        {
            Destroy(item);
        }
        spawnedAreaObjects.Clear();

        AddStoneRoad(new Vector3(0, 0.03f, 0.6f), new Vector3(16.8f, 0.07f, 2.1f));
        AddFenceLine(new Vector3(-10.2f, 0, -6.5f), 5, 1.8f, true);
        AddFenceLine(new Vector3(6.0f, 0, 6.6f), 5, 1.8f, true);

        if (areaId == "village_entrance")
        {
            AddGatehouse(MapPoint(620, 430));
            AddWatchTower(MapPoint(910, 330), 3.9f);
            AddMedievalHouse("Gatekeeper Lodge", MapPoint(310, 500), new Vector3(2.2f, 1.2f, 1.7f), new Color(0.50f, 0.38f, 0.25f), new Color(0.34f, 0.12f, 0.10f));
            AddWaterMill(MapPoint(1080, 470));
            AddLanternPost(MapPoint(520, 610));
            AddLanternPost(MapPoint(820, 610));
        }
        else if (areaId == "village_square")
        {
            AddFountain(MapPoint(650, 575));
            AddMedievalHouse("Notice Hall", MapPoint(780, 270), new Vector3(3.2f, 1.6f, 1.8f), new Color(0.58f, 0.46f, 0.34f), new Color(0.28f, 0.12f, 0.08f));
            AddMedievalHouse("Guild House", MapPoint(330, 470), new Vector3(2.6f, 1.3f, 1.7f), new Color(0.54f, 0.42f, 0.31f), new Color(0.24f, 0.18f, 0.14f));
            AddRunestone(MapPoint(945, 445));
            AddLanternPost(MapPoint(520, 690));
            AddLanternPost(MapPoint(830, 690));
        }
        else if (areaId == "village_market")
        {
            AddMarketStall(MapPoint(760, 470), new Color(0.72f, 0.23f, 0.16f));
            AddMarketStall(MapPoint(930, 610), new Color(0.18f, 0.36f, 0.66f));
            AddCrateStack(MapPoint(530, 840));
            AddBarrelCluster(MapPoint(380, 690));
            AddMedievalHouse("Apothecary", MapPoint(330, 400), new Vector3(2.5f, 1.35f, 1.6f), new Color(0.48f, 0.42f, 0.34f), new Color(0.16f, 0.25f, 0.22f));
            AddLanternPost(MapPoint(660, 650));
            AddLanternPost(MapPoint(1040, 720));
        }
        else if (areaId == "hunting_forest")
        {
            AddForestRing();
            AddHunterCamp(MapPoint(860, 390));
            AddRunestone(MapPoint(540, 640));
            AddCampfire(MapPoint(760, 560));
            AddFenceLine(MapPoint(310, 430), 4, 1.4f, false);
        }
        else if (areaId == "village_rest_area")
        {
            AddMedievalHouse("Rest Cabin", MapPoint(1030, 360), new Vector3(3.0f, 1.6f, 2.0f), new Color(0.53f, 0.39f, 0.25f), new Color(0.24f, 0.12f, 0.08f));
            AddCampfire(MapPoint(690, 760));
            AddBarrelCluster(MapPoint(920, 620));
            AddMedievalHouse("Healer Hut", MapPoint(470, 450), new Vector3(2.3f, 1.25f, 1.6f), new Color(0.43f, 0.47f, 0.38f), new Color(0.18f, 0.30f, 0.18f));
            AddLanternPost(MapPoint(760, 650));
            AddTree(MapPoint(260, 390));
            AddTree(MapPoint(1180, 690));
        }
    }

    private void RebuildHotspots(string areaId)
    {
        foreach (HotspotView view in hotspotViews)
        {
            Destroy(view.root);
        }
        hotspotViews.Clear();

        foreach (HotspotDef def in areas[areaId].hotspots)
        {
            GameObject root = new GameObject("Hotspot - " + def.label);
            root.transform.SetParent(hotspotRoot, false);
            root.transform.position = def.position;

            GameObject marker = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            marker.transform.SetParent(root.transform, false);
            marker.transform.localScale = new Vector3(0.45f, 0.08f, 0.45f);
            marker.transform.localPosition = new Vector3(0, 0.08f, 0);
            marker.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(new Color(0.95f, 0.72f, 0.28f), 0.1f, 0.2f);

            TextMesh label = AddWorldLabel(root.transform, def.label, new Vector3(0, 0.75f, 0), 42, new Color(1.0f, 0.89f, 0.48f));
            hotspotViews.Add(new HotspotView(def, root, marker.GetComponent<Renderer>(), label));
        }
    }

    private void MovePlayer()
    {
        if (IsTyping())
        {
            return;
        }

        float x = Input.GetAxisRaw("Horizontal");
        float z = Input.GetAxisRaw("Vertical");
        Vector3 cameraForward = Vector3.forward;
        Vector3 cameraRight = Vector3.right;
        if (worldCamera != null)
        {
            cameraForward = Vector3.ProjectOnPlane(worldCamera.transform.forward, Vector3.up).normalized;
            cameraRight = Vector3.ProjectOnPlane(worldCamera.transform.right, Vector3.up).normalized;
            if (cameraForward.sqrMagnitude < 0.001f)
            {
                cameraForward = Vector3.forward;
            }
            if (cameraRight.sqrMagnitude < 0.001f)
            {
                cameraRight = Vector3.right;
            }
        }

        Vector3 direction = cameraRight * x + cameraForward * z;
        if (direction.sqrMagnitude > 1)
        {
            direction.Normalize();
        }

        if (direction.sqrMagnitude > 0.001f)
        {
            playerObject.transform.position += direction * playerSpeed * Time.deltaTime;
            Vector3 p = playerObject.transform.position;
            p.x = Mathf.Clamp(p.x, -10.5f, 10.5f);
            p.z = Mathf.Clamp(p.z, -7.2f, 7.4f);
            playerObject.transform.position = p;
            playerObject.transform.rotation = Quaternion.LookRotation(direction, Vector3.up);
        }
    }

    private void UpdateCameraFollow(bool instant)
    {
        if (worldCamera == null || playerObject == null)
        {
            return;
        }

        Vector3 playerPosition = playerObject.transform.position;
        Vector3 lookTarget = playerPosition + cameraLookOffset;
        Quaternion cameraRotation = Quaternion.Euler(cameraPitch, cameraYaw, 0.0f);
        Vector3 desiredPosition = lookTarget + cameraRotation * new Vector3(0.0f, 0.0f, -cameraDistance);
        if (instant)
        {
            worldCamera.transform.position = desiredPosition;
            cameraVelocity = Vector3.zero;
        }
        else
        {
            worldCamera.transform.position = Vector3.SmoothDamp(worldCamera.transform.position, desiredPosition, ref cameraVelocity, cameraFollowSmoothTime);
        }

        worldCamera.transform.rotation = Quaternion.LookRotation(lookTarget - worldCamera.transform.position, Vector3.up);
    }

    private void UpdateInteractionState()
    {
        string nearestNpc = "";
        float nearestNpcDistance = float.MaxValue;
        foreach (KeyValuePair<string, ActorView> pair in actors)
        {
            if (pair.Key == PlayerActorId || !pair.Value.root.activeSelf)
            {
                continue;
            }

            float distance = Vector3.Distance(playerObject.transform.position, pair.Value.root.transform.position);
            if (distance < InteractionDistance && distance < nearestNpcDistance)
            {
                nearestNpcDistance = distance;
                nearestNpc = pair.Key;
            }
        }

        HotspotView nearestHotspot = null;
        float nearestHotspotDistance = float.MaxValue;
        foreach (HotspotView hotspot in hotspotViews)
        {
            float distance = Vector3.Distance(playerObject.transform.position, hotspot.root.transform.position);
            if (distance < InteractionDistance && distance < nearestHotspotDistance)
            {
                nearestHotspotDistance = distance;
                nearestHotspot = hotspot;
            }
        }

        targetNpcId = nearestNpc;
        targetHotspot = nearestHotspot;

        foreach (KeyValuePair<string, ActorView> pair in actors)
        {
            if (pair.Key == PlayerActorId)
            {
                continue;
            }
            pair.Value.SetHighlighted(pair.Key == targetNpcId || pair.Key == selectedNpcId);
        }

        foreach (HotspotView hotspot in hotspotViews)
        {
            hotspot.SetHighlighted(hotspot == targetHotspot);
        }

        UpdateSelectedLabel();
    }

    private void HandleHotkeys()
    {
        if (IsTyping())
        {
            return;
        }

        if (Input.GetKeyDown(KeyCode.E))
        {
            InteractWithCurrentTarget();
        }
        else if (Input.GetKeyDown(KeyCode.T))
        {
            OnAdvanceTickPressed();
        }
        else if (Input.GetKeyDown(KeyCode.O))
        {
            OnSuspiciousEventPressed();
        }
        else if (Input.GetKeyDown(KeyCode.P))
        {
            OnPlanExecutePressed();
        }
        else if (Input.GetKeyDown(KeyCode.R))
        {
            OnResetPressed();
        }
    }

    private void HandleCursorToggle()
    {
        if (!Input.GetKeyDown(KeyCode.Tab))
        {
            return;
        }

        SetCursorLook(!cursorLookEnabled);
    }

    private void SetCursorLook(bool enabled)
    {
        cursorLookEnabled = enabled;
        Cursor.lockState = enabled ? CursorLockMode.Locked : CursorLockMode.None;
        Cursor.visible = !enabled;

        if (enabled && EventSystem.current != null)
        {
            EventSystem.current.SetSelectedGameObject(null);
        }
    }

    private void UpdateMouseLook()
    {
        if (!cursorLookEnabled || worldCamera == null)
        {
            return;
        }

        cameraYaw += Input.GetAxis("Mouse X") * mouseSensitivity;
        cameraPitch -= Input.GetAxis("Mouse Y") * mouseSensitivity;
        cameraPitch = Mathf.Clamp(cameraPitch, minCameraPitch, maxCameraPitch);
    }

    private void InteractWithCurrentTarget()
    {
        if (!string.IsNullOrEmpty(targetNpcId))
        {
            SelectNpc(targetNpcId, true);
            return;
        }

        if (targetHotspot == null)
        {
            SetStatus("附近没有可交互对象。");
            return;
        }

        HotspotDef def = targetHotspot.def;
        if (def.kind == "transition" && !string.IsNullOrEmpty(def.targetArea))
        {
            SwitchArea(def.targetArea, def.detail, null);
        }
        else if (def.kind == "focus_npc" && !string.IsNullOrEmpty(def.npcId))
        {
            SelectNpc(def.npcId, true);
            AppendEventDetail(def.detail);
        }
        else
        {
            AppendEventDetail(def.label + "\n" + def.detail);
            SetStatus(def.detail);
        }
    }

    private void SelectNpc(string npcId, bool fetchHistory)
    {
        selectedNpcId = npcId;
        UpdateSelectedLabel();
        if (actors.ContainsKey(npcId))
        {
            SetStatus("已选择 " + actors[npcId].displayName + "。");
        }
        if (fetchHistory)
        {
            RequestDialogueHistory(npcId);
            RequestInventory(npcId);
        }
    }

    private void OnSubmitPressed()
    {
        string npcId = !string.IsNullOrEmpty(targetNpcId) ? targetNpcId : selectedNpcId;
        if (string.IsNullOrEmpty(npcId))
        {
            SetStatus("附近没有可对话 NPC。");
            return;
        }

        string content = speechInput.text.Trim();
        if (string.IsNullOrEmpty(content))
        {
            SetStatus("请输入对话内容。");
            return;
        }

        currentTick++;
        UpdateTickLabel();
        SelectNpc(npcId, false);
        if (actors.ContainsKey(npcId))
        {
            actors[npcId].ShowSpeech("...");
        }

        Dictionary<string, object> body = new Dictionary<string, object>
        {
            {"speaker_id", PlayerId},
            {"content", content},
            {"created_at_tick", currentTick}
        };
        SetStatus("正在向 " + DisplayName(npcId) + " 发送对话。");
        api.Post("/npcs/" + npcId + "/utterances", body, obj => OnPlayerUtteranceReceived(npcId, obj), message => OnRequestFailed("玩家发言", message));
    }

    private void OnPlayerUtteranceReceived(string fallbackNpcId, object obj)
    {
        Dictionary<string, object> result = AsDict(obj);
        string npcId = GetString(result, "npc_id", fallbackNpcId);
        string reply = GetString(result, "npc_reply", "");
        if (actors.ContainsKey(npcId))
        {
            actors[npcId].ShowSpeech(reply);
        }
        speechInput.text = "";
        SetStatus("对话已返回。来源=" + GetString(result, "source", "?"));
        RequestDialogueHistory(npcId);
        api.Get("/npcs", OnNpcListReceived, message => OnRequestFailed("NPC 列表", message));
    }

    private void OnPlanExecutePressed()
    {
        if (string.IsNullOrEmpty(selectedNpcId))
        {
            SetStatus("请先靠近并按 E 选择一个 NPC。");
            return;
        }

        pendingPlanThenExecute = true;
        SetStatus("正在为 " + DisplayName(selectedNpcId) + " 规划并执行任务。");
        api.Post("/npcs/" + selectedNpcId + "/plan", null, OnPlanApplied, message => OnRequestFailed("行动规划", message));
    }

    private void OnPlanApplied(object obj)
    {
        Dictionary<string, object> result = AsDict(obj);
        string npcId = GetString(result, "npc_id", selectedNpcId);
        taskLog.text = "规划 NPC：" + DisplayName(npcId) + "\n模式：" + GetString(result, "mode", "") + "\n任务：" + FormatTask(GetValue(result, "selected_task"));
        thoughtLog.text = FormatThought(GetValue(result, "thought"));
        if (pendingPlanThenExecute && !string.IsNullOrEmpty(npcId))
        {
            pendingPlanThenExecute = false;
            api.Post("/npcs/" + npcId + "/execute-task", null, OnTaskExecuted, message => OnRequestFailed("任务执行", message));
            return;
        }

        SetStatus(DisplayName(npcId) + " 的规划已更新。");
        api.Get("/npcs", OnNpcListReceived, message => OnRequestFailed("NPC 列表", message));
    }

    private void OnTaskExecuted(object obj)
    {
        Dictionary<string, object> result = AsDict(obj);
        string npcId = GetString(result, "npc_id", selectedNpcId);
        taskLog.text = "执行 NPC：" + DisplayName(npcId) + "\n当前任务：" + FormatTask(GetValue(result, "executed_task")) + "\n下一任务：" + FormatTask(GetValue(result, "next_current_task"));
        object worldEffects = GetValue(result, "world_effects");
        if (worldEffects != null)
        {
            taskLog.text += "\nworld=" + MiniJson.Serialize(worldEffects);
        }
        SetStatus(DisplayName(npcId) + " 已执行当前任务。");
        RefreshBackendState();
    }

    private void OnAdvanceTickPressed()
    {
        RequestNextTick(false);
    }

    private void RequestNextTick(bool fromAuto)
    {
        if (tickRequestInFlight)
        {
            return;
        }

        tickRequestInFlight = true;
        currentTick++;
        UpdateTickLabel();
        SetStatus("正在推进 tick " + currentTick + "。");
        Dictionary<string, object> body = new Dictionary<string, object>
        {
            {"current_tick", currentTick},
            {"npc_ids", new List<object>()},
            {"include_profile", true},
            {"enable_world_updates", true}
        };
        api.Post("/simulation/tick", body, OnSimulationTickCompleted, message =>
        {
            tickRequestInFlight = false;
            autoTickEnabled = false;
            UpdateAutoTickButton();
            OnRequestFailed("Tick 推进", message);
        });
    }

    private void OnSimulationTickCompleted(object obj)
    {
        tickRequestInFlight = false;
        Dictionary<string, object> result = AsDict(obj);
        currentTick = GetInt(result, "current_tick", currentTick);
        UpdateTickLabel();
        thoughtLog.text = FormatTickProfile(GetValue(result, "profile"));
        taskLog.text = FormatTickResults(GetValue(result, "npc_results"));
        object worldUpdate = GetValue(result, "world_update");
        if (worldUpdate != null)
        {
            AppendEventDetail(FormatWorldUpdate(worldUpdate));
        }
        SetStatus("tick " + currentTick + " 已完成。");
        RefreshBackendState();
    }

    private void OnAutoTickPressed()
    {
        autoTickEnabled = !autoTickEnabled;
        float parsed;
        if (float.TryParse(autoTickInput.text, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed))
        {
            autoTickInterval = Mathf.Clamp(parsed, 0.2f, 10.0f);
        }
        autoTickTimer = autoTickInterval;
        UpdateAutoTickButton();
        SetStatus(autoTickEnabled ? "自动推进已启动。" : "自动推进已暂停。");
    }

    private void UpdateAutoTick()
    {
        if (!autoTickEnabled)
        {
            return;
        }

        autoTickTimer -= Time.deltaTime;
        if (autoTickTimer <= 0)
        {
            autoTickTimer = Mathf.Max(0.2f, autoTickInterval);
            RequestNextTick(true);
        }
    }

    private void OnResetPressed()
    {
        autoTickEnabled = false;
        UpdateAutoTickButton();
        SetStatus("正在重置世界。");
        api.Post("/debug/reset", null, OnWorldReset, message => OnRequestFailed("世界重置", message));
    }

    private void OnWorldReset(object obj)
    {
        currentTick = 0;
        selectedNpcId = "";
        targetNpcId = "";
        speechInput.text = "";
        dialogueLog.text = "世界已重置，等待重新载入 NPC 状态。";
        thoughtLog.text = "思考与规划结果会显示在这里。";
        taskLog.text = "任务执行结果会显示在这里。";
        eventLog.text = "世界事件记录会显示在这里。";
        eventDetailLog.text = "建筑、热点、资源和经济状态会显示在这里。";
        foreach (ActorView actor in actors.Values)
        {
            actor.ShowSpeech("");
        }
        UpdateTickLabel();
        SwitchArea("village_entrance", "世界已重置，回到村庄入口。", null);
        RefreshBackendState();
    }

    private void OnSuspiciousEventPressed()
    {
        SubmitWorldEvent("suspicious_arrival", "traveler_unknown", "发现可疑来客");
    }

    private void OnMonsterEventPressed()
    {
        SubmitWorldEvent("monster_appeared", "monster_wolf_001", "林地出现怪物");
    }

    private void OnResourceEventPressed()
    {
        SubmitWorldEvent("food_shortage", "market_supply", "集市补给短缺");
    }

    private void OnTheftEventPressed()
    {
        SubmitWorldEvent("player_stole", PlayerId, "有人报告偷窃");
    }

    private void SubmitWorldEvent(string eventType, string actorId, string detail)
    {
        currentTick++;
        UpdateTickLabel();
        Dictionary<string, object> payload = new Dictionary<string, object>
        {
            {"detail", detail},
            {"source", "unity_3d_demo"}
        };
        Dictionary<string, object> worldEvent = new Dictionary<string, object>
        {
            {"event_id", eventType + "_" + currentTick},
            {"event_type", eventType},
            {"actor_id", actorId},
            {"target_id", null},
            {"location_id", CurrentLocationId()},
            {"payload", payload},
            {"importance", 70},
            {"created_at_tick", currentTick}
        };
        SetStatus("正在注入事件：" + detail + "。");
        api.Post("/events", worldEvent, OnEventIngested, message => OnRequestFailed("事件注入", message));
    }

    private void OnEventIngested(object obj)
    {
        AppendEventDetail("事件已注入：" + MiniJson.Serialize(obj));
        RefreshBackendState();
    }

    private void OnNpcListReceived(object obj)
    {
        List<object> list = AsList(obj);
        foreach (object item in list)
        {
            Dictionary<string, object> state = AsDict(item);
            string npcId = GetString(state, "npc_id", "");
            if (string.IsNullOrEmpty(npcId))
            {
                continue;
            }
            EnsureNpcActor(state);
            UpdateNpcActor(state);
        }

        UpdateActorVisibility();
        SetStatus("已载入 " + list.Count + " 个 NPC。");
    }

    private void EnsureNpcActor(Dictionary<string, object> state)
    {
        string npcId = GetString(state, "npc_id", "");
        if (actors.ContainsKey(npcId))
        {
            return;
        }

        string role = GetString(state, "role", "villager");
        string displayName = GetString(state, "name", npcId);
        GameObject actorObject = CreateActorObject(npcId, displayName, RoleColor(npcId, role));
        actors[npcId] = new ActorView(npcId, displayName, role, AreaForNpcState(npcId, state), actorObject);
    }

    private void UpdateNpcActor(Dictionary<string, object> state)
    {
        string npcId = GetString(state, "npc_id", "");
        if (!actors.ContainsKey(npcId))
        {
            return;
        }

        ActorView actor = actors[npcId];
        actor.displayName = GetString(state, "name", actor.displayName);
        actor.role = GetString(state, "role", actor.role);
        actor.areaId = AreaForNpcState(npcId, state);
        actor.nameLabel.text = actor.displayName;
        actor.root.transform.position = NpcStandPosition(npcId, actor.areaId);
        actor.tooltipLabel.text = FormatNpcTooltip(state);
    }

    private void UpdateActorVisibility()
    {
        foreach (KeyValuePair<string, ActorView> pair in actors)
        {
            if (pair.Key == PlayerActorId)
            {
                pair.Value.root.SetActive(true);
                continue;
            }
            pair.Value.root.SetActive(pair.Value.areaId == currentAreaId);
        }
    }

    private void OnDialogueHistoryReceived(string npcId, object obj)
    {
        Dictionary<string, object> history = AsDict(obj);
        List<string> lines = new List<string>();
        string summary = GetString(history, "summary", "").Trim();
        if (!string.IsNullOrEmpty(summary))
        {
            lines.Add("摘要：" + summary);
            lines.Add("");
        }

        List<object> turns = AsList(GetValue(history, "recent_turns"));
        foreach (object turnObj in turns)
        {
            Dictionary<string, object> turn = AsDict(turnObj);
            lines.Add("[" + GetString(turn, "speaker_label", GetString(turn, "speaker_id", "?")) + "] " + GetString(turn, "content", ""));
        }

        dialogueLog.text = lines.Count > 0 ? string.Join("\n", lines.ToArray()) : "还没有对话记录。";
    }

    private void OnEventLogReceived(object obj)
    {
        List<object> events = AsList(obj);
        List<string> lines = new List<string>();
        foreach (object item in events)
        {
            Dictionary<string, object> e = AsDict(item);
            lines.Add("[t" + GetString(e, "created_at_tick", "?") + "] " + GetString(e, "event_type", "") + " | actor=" + GetString(e, "actor_id", "-") + " | location=" + GetString(e, "location_id", "-"));
        }
        eventLog.text = lines.Count > 0 ? string.Join("\n", lines.ToArray()) : "暂无世界事件。";
    }

    private void OnWorldResourcesReceived(object obj)
    {
        ClearDynamicObjects("resource");
        List<object> resources = AsList(obj);
        int index = 0;
        foreach (object item in resources)
        {
            Dictionary<string, object> resource = AsDict(item);
            Vector3 pos = ResourceMarkerPosition(index);
            GameObject marker = AddPropCylinder("resource:" + GetString(resource, "node_id", index.ToString()), pos + Vector3.up * 0.15f, 0.35f, 0.3f, new Color(0.36f, 0.72f, 0.30f), false);
            marker.transform.SetParent(dynamicRoot, true);
            AddWorldLabel(marker.transform, GetString(resource, "display_name", GetString(resource, "resource_type", "resource")) + " x" + GetString(resource, "available_quantity", "0"), new Vector3(0, 0.75f, 0), 38, new Color(0.83f, 1.0f, 0.67f));
            dynamicWorldObjects.Add(marker);
            index++;
        }
    }

    private void OnWorldEntitiesReceived(object obj)
    {
        ClearDynamicObjects("entity");
        List<object> entities = AsList(obj);
        int index = 0;
        foreach (object item in entities)
        {
            Dictionary<string, object> entity = AsDict(item);
            string type = GetString(entity, "entity_type", "");
            Vector3 pos = EntityMarkerPosition(index);
            GameObject marker = GameObject.CreatePrimitive(type == "monster" ? PrimitiveType.Capsule : PrimitiveType.Sphere);
            marker.name = "entity:" + GetString(entity, "entity_id", index.ToString());
            marker.transform.SetParent(dynamicRoot, false);
            marker.transform.position = pos + Vector3.up * 0.45f;
            marker.transform.localScale = new Vector3(0.75f, 0.9f, 0.75f);
            marker.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(type == "monster" ? new Color(0.84f, 0.22f, 0.16f) : new Color(0.42f, 0.72f, 0.95f), 0.2f, 0.25f);
            AddWorldLabel(marker.transform, GetString(entity, "display_name", GetString(entity, "entity_id", "")) + " [" + GetString(entity, "state", "") + "]", new Vector3(0, 1.15f, 0), 36, Color.white);
            dynamicWorldObjects.Add(marker);
            index++;
        }
    }

    private void ClearDynamicObjects(string prefix)
    {
        for (int i = dynamicWorldObjects.Count - 1; i >= 0; i--)
        {
            if (dynamicWorldObjects[i] == null)
            {
                dynamicWorldObjects.RemoveAt(i);
                continue;
            }
            if (dynamicWorldObjects[i].name.StartsWith(prefix, StringComparison.Ordinal))
            {
                Destroy(dynamicWorldObjects[i]);
                dynamicWorldObjects.RemoveAt(i);
            }
        }
    }

    private void RequestDialogueHistory(string npcId)
    {
        api.Get("/npcs/" + npcId + "/dialogue-history?speaker_id=" + PlayerId + "&recent_turn_limit=6", obj => OnDialogueHistoryReceived(npcId, obj), message => OnRequestFailed("对话历史", message));
    }

    private void RequestInventory(string npcId)
    {
        api.Get("/npcs/" + npcId + "/inventory", obj => OnInventoryReceived(npcId, obj), message => OnRequestFailed("NPC Inventory", message));
    }

    private void OnInventoryReceived(string npcId, object obj)
    {
        List<object> inventory = AsList(obj);
        if (inventory.Count == 0)
        {
            return;
        }

        List<string> parts = new List<string>();
        foreach (object itemObj in inventory)
        {
            Dictionary<string, object> item = AsDict(itemObj);
            parts.Add(GetString(item, "item_type", "") + " x" + GetString(item, "quantity", "0"));
        }
        AppendEventDetail(DisplayName(npcId) + " inventory: " + string.Join(", ", parts.ToArray()));
    }

    private void OnRequestFailed(string label, string message)
    {
        SetStatus(label + "失败：" + message);
        AppendEventDetail(label + "失败：" + message);
    }

    private void UpdateSelectedLabel()
    {
        string text = "附近 NPC：";
        text += !string.IsNullOrEmpty(targetNpcId) ? DisplayName(targetNpcId) : "无";
        if (targetHotspot != null)
        {
            text += " | 热点：" + targetHotspot.def.label;
        }
        if (!string.IsNullOrEmpty(selectedNpcId))
        {
            text += "\n已选择：" + DisplayName(selectedNpcId);
        }
        selectedLabel.text = text;
    }

    private void UpdateTickLabel()
    {
        tickLabel.text = "Tick " + currentTick;
    }

    private void SetStatus(string text)
    {
        statusLabel.text = "状态：" + text;
    }

    private void AppendEventDetail(string text)
    {
        string current = eventDetailLog == null ? "" : eventDetailLog.text.Trim();
        eventDetailLog.text = string.IsNullOrEmpty(current) ? text : text + "\n\n" + current;
    }

    private void UpdateAutoTickButton()
    {
        if (autoTickButton != null)
        {
            autoTickButton.GetComponentInChildren<Text>().text = autoTickEnabled ? "自动推进：开" : "自动推进：关";
        }
    }

    private string CurrentLocationId()
    {
        return locationByArea.ContainsKey(currentAreaId) ? locationByArea[currentAreaId] : "village_square";
    }

    private string AreaForNpcState(string npcId, Dictionary<string, object> state)
    {
        string location = GetString(state, "location_id", "");
        if (areaByLocation.ContainsKey(location))
        {
            return areaByLocation[location];
        }
        if (npcAreaPositions.ContainsKey(npcId))
        {
            foreach (string areaId in npcAreaPositions[npcId].Keys)
            {
                return areaId;
            }
        }
        return "village_square";
    }

    private Vector3 NpcStandPosition(string npcId, string areaId)
    {
        if (npcAreaPositions.ContainsKey(npcId) && npcAreaPositions[npcId].ContainsKey(areaId))
        {
            return npcAreaPositions[npcId][areaId];
        }
        return MapPoint(650, 700);
    }

    private Vector3 DefaultSpawnForArea(string areaId)
    {
        if (areaId == "village_entrance") return MapPoint(460, 780);
        if (areaId == "village_square") return MapPoint(655, 800);
        if (areaId == "village_market") return MapPoint(640, 820);
        if (areaId == "hunting_forest") return MapPoint(635, 835);
        return MapPoint(625, 815);
    }

    private Vector3 ResourceMarkerPosition(int index)
    {
        if (currentAreaId == "hunting_forest") return MapPoint(120, 180 + index * 45);
        if (currentAreaId == "village_market") return MapPoint(150, 820 + index * 45);
        return MapPoint(120, 160 + index * 45);
    }

    private Vector3 EntityMarkerPosition(int index)
    {
        if (currentAreaId == "hunting_forest") return MapPoint(880 + (index % 2) * 80, 430 + (index / 2) * 90);
        if (currentAreaId == "village_entrance") return MapPoint(860 + (index % 2) * 70, 540 + (index / 2) * 86);
        if (currentAreaId == "village_market") return MapPoint(960 + (index % 2) * 72, 520 + (index / 2) * 90);
        return MapPoint(940 + (index % 2) * 72, 440 + (index / 2) * 90);
    }

    private Vector3 MapPoint(float godotX, float godotY)
    {
        return new Vector3((godotX / 1344.0f - 0.5f) * 22.0f, 0, (0.5f - godotY / 1080.0f) * 16.0f);
    }

    private GameObject CreateActorObject(string actorId, string displayName, Color color)
    {
        GameObject root = new GameObject("Actor - " + actorId);
        root.transform.SetParent(actorRoot, false);

        GameObject body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        body.name = "Body";
        body.transform.SetParent(root.transform, false);
        body.transform.localPosition = new Vector3(0, 0.75f, 0);
        body.transform.localScale = new Vector3(0.75f, 0.75f, 0.75f);
        body.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(color, 0.3f, 0.25f);

        GameObject shadow = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        shadow.name = "Shadow";
        shadow.transform.SetParent(root.transform, false);
        shadow.transform.localPosition = new Vector3(0, 0.03f, 0);
        shadow.transform.localScale = new Vector3(0.75f, 0.025f, 0.75f);
        shadow.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(new Color(0, 0, 0, 0.35f), 0, 0);

        TextMesh nameLabel = AddWorldLabel(root.transform, displayName, new Vector3(0, 1.85f, 0), 42, new Color(0.98f, 0.96f, 0.86f));
        TextMesh speech = AddWorldLabel(root.transform, "", new Vector3(0, 2.45f, 0), 34, Color.white);
        TextMesh tooltip = AddWorldLabel(root.transform, "", new Vector3(0, -0.35f, 0), 26, new Color(0.75f, 0.88f, 1.0f));
        tooltip.gameObject.SetActive(false);

        ActorView view = new ActorView(actorId, displayName, "", currentAreaId, root);
        view.bodyRenderer = body.GetComponent<Renderer>();
        view.nameLabel = nameLabel;
        view.speechLabel = speech;
        view.tooltipLabel = tooltip;
        return root;
    }

    private TextMesh AddWorldLabel(Transform parent, string text, Vector3 localPosition, int fontSize, Color color)
    {
        GameObject labelObject = new GameObject("Label");
        labelObject.transform.SetParent(parent, false);
        labelObject.transform.localPosition = localPosition;
        TextMesh label = labelObject.AddComponent<TextMesh>();
        label.text = text;
        label.anchor = TextAnchor.MiddleCenter;
        label.alignment = TextAlignment.Center;
        label.characterSize = 0.045f;
        label.fontSize = fontSize;
        label.color = color;
        return label;
    }

    private Font CreateReadableFont()
    {
        Font font = Font.CreateDynamicFontFromOSFont(new[] {"Microsoft YaHei", "SimHei", "Arial"}, 16);
        return font != null ? font : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
    }

    private void AddStoneRoad(Vector3 position, Vector3 scale)
    {
        AddPropCube("Packed Dirt Road", position, scale, new Color(0.36f, 0.31f, 0.24f));
        for (int i = 0; i < 12; i++)
        {
            float x = -7.6f + i * 1.35f;
            float z = 0.6f + ((i % 2 == 0) ? -0.58f : 0.58f);
            AddPropCube("Road Stone", new Vector3(x, 0.09f, z), new Vector3(0.55f, 0.045f, 0.38f), new Color(0.45f, 0.43f, 0.38f));
        }
    }

    private void AddMedievalHouse(string name, Vector3 basePosition, Vector3 bodySize, Color wallColor, Color roofColor)
    {
        AddPropCube(name + " Stone Base", basePosition + Vector3.up * 0.12f, new Vector3(bodySize.x + 0.25f, 0.24f, bodySize.z + 0.22f), new Color(0.34f, 0.33f, 0.30f));
        AddPropCube(name + " Timber Body", basePosition + Vector3.up * (0.24f + bodySize.y * 0.5f), bodySize, wallColor);
        AddGabledRoof(name + " Steep Roof", basePosition + Vector3.up * (0.36f + bodySize.y), new Vector3(bodySize.x + 0.55f, bodySize.y * 0.55f, bodySize.z + 0.55f), roofColor);

        AddPropCube(name + " Door", basePosition + new Vector3(0, 0.55f, -bodySize.z * 0.52f - 0.02f), new Vector3(0.52f, 0.9f, 0.06f), new Color(0.20f, 0.12f, 0.07f));
        AddPropCube(name + " Left Window", basePosition + new Vector3(-bodySize.x * 0.32f, 0.95f, -bodySize.z * 0.53f - 0.03f), new Vector3(0.32f, 0.28f, 0.05f), new Color(0.95f, 0.73f, 0.35f));
        AddPropCube(name + " Right Window", basePosition + new Vector3(bodySize.x * 0.32f, 0.95f, -bodySize.z * 0.53f - 0.03f), new Vector3(0.32f, 0.28f, 0.05f), new Color(0.95f, 0.73f, 0.35f));
        AddPropCube(name + " Chimney", basePosition + new Vector3(bodySize.x * 0.28f, bodySize.y + 1.05f, 0.12f), new Vector3(0.32f, 0.85f, 0.32f), new Color(0.25f, 0.23f, 0.21f));
        AddPropCube(name + " Front Beam", basePosition + new Vector3(0, 1.22f, -bodySize.z * 0.55f), new Vector3(bodySize.x + 0.12f, 0.16f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube(name + " Left Beam", basePosition + new Vector3(-bodySize.x * 0.52f, 0.86f, -bodySize.z * 0.55f), new Vector3(0.12f, 1.18f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube(name + " Right Beam", basePosition + new Vector3(bodySize.x * 0.52f, 0.86f, -bodySize.z * 0.55f), new Vector3(0.12f, 1.18f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
    }

    private void AddGatehouse(Vector3 position)
    {
        AddPropCube("Gate Left Tower Base", position + new Vector3(-2.5f, 1.05f, 0), new Vector3(1.25f, 2.1f, 1.15f), new Color(0.47f, 0.45f, 0.40f));
        AddPropCube("Gate Right Tower Base", position + new Vector3(2.5f, 1.05f, 0), new Vector3(1.25f, 2.1f, 1.15f), new Color(0.47f, 0.45f, 0.40f));
        AddPropCube("Gate Crosswall", position + new Vector3(0, 1.75f, 0), new Vector3(6.0f, 0.75f, 0.8f), new Color(0.52f, 0.50f, 0.45f));
        AddPropCube("Gate Opening Shadow", position + new Vector3(0, 0.73f, -0.42f), new Vector3(1.55f, 1.45f, 0.08f), new Color(0.05f, 0.04f, 0.035f));
        AddPropCube("Portcullis Bar A", position + new Vector3(-0.45f, 0.75f, -0.48f), new Vector3(0.08f, 1.35f, 0.08f), new Color(0.08f, 0.08f, 0.075f));
        AddPropCube("Portcullis Bar B", position + new Vector3(0.0f, 0.75f, -0.48f), new Vector3(0.08f, 1.35f, 0.08f), new Color(0.08f, 0.08f, 0.075f));
        AddPropCube("Portcullis Bar C", position + new Vector3(0.45f, 0.75f, -0.48f), new Vector3(0.08f, 1.35f, 0.08f), new Color(0.08f, 0.08f, 0.075f));
        AddGabledRoof("Gate Slate Roof", position + new Vector3(0, 2.45f, 0), new Vector3(6.45f, 0.9f, 1.45f), new Color(0.20f, 0.20f, 0.24f));
        AddPropCube("Gate Banner", position + new Vector3(0, 1.55f, -0.55f), new Vector3(0.55f, 0.9f, 0.04f), new Color(0.54f, 0.08f, 0.12f));
    }

    private void AddWatchTower(Vector3 position, float height)
    {
        AddPropCylinder("Watchtower Stone Footing", position + Vector3.up * 0.22f, 0.78f, 0.45f, new Color(0.38f, 0.36f, 0.32f));
        AddPropCube("Watchtower Timber Shaft", position + Vector3.up * (height * 0.45f), new Vector3(1.25f, height * 0.9f, 1.25f), new Color(0.34f, 0.22f, 0.13f));
        AddPropCube("Watchtower Platform", position + Vector3.up * height, new Vector3(2.0f, 0.24f, 2.0f), new Color(0.26f, 0.16f, 0.09f));
        AddPropCube("Watchtower Rail Front", position + new Vector3(0, height + 0.38f, -1.0f), new Vector3(2.05f, 0.18f, 0.14f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube("Watchtower Rail Back", position + new Vector3(0, height + 0.38f, 1.0f), new Vector3(2.05f, 0.18f, 0.14f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube("Watchtower Rail Left", position + new Vector3(-1.0f, height + 0.38f, 0), new Vector3(0.14f, 0.18f, 2.05f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube("Watchtower Rail Right", position + new Vector3(1.0f, height + 0.38f, 0), new Vector3(0.14f, 0.18f, 2.05f), new Color(0.22f, 0.13f, 0.07f));
        AddCone("Watchtower Roof", position + Vector3.up * (height + 0.85f), 1.32f, 1.05f, new Color(0.23f, 0.09f, 0.08f));
    }

    private void AddWaterMill(Vector3 position)
    {
        AddMedievalHouse("Water Mill House", position + new Vector3(-0.9f, 0, 0.15f), new Vector3(1.8f, 1.15f, 1.45f), new Color(0.46f, 0.38f, 0.29f), new Color(0.18f, 0.14f, 0.10f));
        GameObject wheel = AddPropCylinder("Water Wheel", position + new Vector3(0.65f, 0.88f, -0.75f), 0.78f, 0.20f, new Color(0.22f, 0.13f, 0.07f));
        wheel.transform.rotation = Quaternion.Euler(90, 0, 0);
        for (int i = 0; i < 6; i++)
        {
            GameObject spoke = AddPropCube("Water Wheel Spoke", position + new Vector3(0.65f, 0.88f, -0.75f), new Vector3(1.45f, 0.055f, 0.055f), new Color(0.16f, 0.09f, 0.05f));
            spoke.transform.rotation = Quaternion.Euler(0, 0, i * 30.0f);
        }
        AddPropCube("Mill Water Channel", position + new Vector3(1.2f, 0.08f, -0.2f), new Vector3(2.2f, 0.12f, 0.55f), new Color(0.16f, 0.31f, 0.38f));
    }

    private void AddMarketStall(Vector3 position, Color clothColor)
    {
        AddPropCube("Market Stall Table", position + Vector3.up * 0.42f, new Vector3(2.0f, 0.20f, 1.05f), new Color(0.34f, 0.20f, 0.10f));
        AddPropCube("Market Stall Left Post", position + new Vector3(-0.88f, 0.85f, -0.42f), new Vector3(0.10f, 1.45f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube("Market Stall Right Post", position + new Vector3(0.88f, 0.85f, -0.42f), new Vector3(0.10f, 1.45f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube("Market Stall Back Left Post", position + new Vector3(-0.88f, 0.85f, 0.42f), new Vector3(0.10f, 1.45f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
        AddPropCube("Market Stall Back Right Post", position + new Vector3(0.88f, 0.85f, 0.42f), new Vector3(0.10f, 1.45f, 0.10f), new Color(0.22f, 0.13f, 0.07f));
        GameObject canopy = AddPropCube("Market Stall Cloth Canopy", position + Vector3.up * 1.5f, new Vector3(2.35f, 0.12f, 1.42f), clothColor);
        canopy.transform.rotation = Quaternion.Euler(0, 0, -3.0f);
        AddCrateStack(position + new Vector3(1.35f, 0, 0.15f));
    }

    private void AddFountain(Vector3 position)
    {
        AddPropCylinder("Fountain Basin", position + Vector3.up * 0.18f, 1.15f, 0.35f, new Color(0.42f, 0.43f, 0.42f));
        AddPropCylinder("Fountain Water", position + Vector3.up * 0.39f, 0.90f, 0.08f, new Color(0.26f, 0.55f, 0.78f));
        AddPropCylinder("Fountain Pillar", position + Vector3.up * 0.78f, 0.22f, 0.90f, new Color(0.50f, 0.49f, 0.46f));
        AddCone("Fountain Spout", position + Vector3.up * 1.33f, 0.42f, 0.45f, new Color(0.45f, 0.45f, 0.43f));
    }

    private void AddHunterCamp(Vector3 position)
    {
        AddPropCube("Hunter Camp Bedroll", position + new Vector3(-0.9f, 0.14f, 0.25f), new Vector3(1.25f, 0.12f, 0.55f), new Color(0.18f, 0.29f, 0.18f));
        AddPropCube("Hunter Camp Supply Box", position + new Vector3(0.78f, 0.28f, 0.25f), new Vector3(0.85f, 0.55f, 0.65f), new Color(0.34f, 0.20f, 0.10f));
        AddCone("Hunter Hide Tent", position + new Vector3(0.0f, 0.72f, -0.65f), 1.15f, 1.4f, new Color(0.36f, 0.28f, 0.18f));
        AddCampfire(position + new Vector3(0.35f, 0, 1.0f));
    }

    private void AddCampfire(Vector3 position)
    {
        AddPropCylinder("Campfire Stone Ring", position + Vector3.up * 0.08f, 0.62f, 0.16f, new Color(0.29f, 0.28f, 0.25f));
        GameObject logA = AddPropCube("Campfire Log A", position + new Vector3(0.0f, 0.18f, 0), new Vector3(1.0f, 0.14f, 0.16f), new Color(0.22f, 0.12f, 0.06f));
        logA.transform.rotation = Quaternion.Euler(0, 35, 0);
        GameObject logB = AddPropCube("Campfire Log B", position + new Vector3(0.0f, 0.22f, 0), new Vector3(1.0f, 0.14f, 0.16f), new Color(0.22f, 0.12f, 0.06f));
        logB.transform.rotation = Quaternion.Euler(0, -35, 0);
        AddCone("Campfire Flame Outer", position + Vector3.up * 0.55f, 0.38f, 0.72f, new Color(0.95f, 0.32f, 0.08f));
        AddCone("Campfire Flame Inner", position + Vector3.up * 0.62f, 0.22f, 0.62f, new Color(1.0f, 0.82f, 0.22f));
    }

    private void AddRunestone(Vector3 position)
    {
        AddPropCube("Runestone Slab", position + Vector3.up * 0.82f, new Vector3(0.58f, 1.55f, 0.24f), new Color(0.30f, 0.33f, 0.34f));
        AddPropCube("Runestone Rune A", position + new Vector3(0, 1.10f, -0.14f), new Vector3(0.36f, 0.06f, 0.035f), new Color(0.26f, 0.85f, 0.78f));
        AddPropCube("Runestone Rune B", position + new Vector3(0, 0.82f, -0.14f), new Vector3(0.06f, 0.36f, 0.035f), new Color(0.26f, 0.85f, 0.78f));
    }

    private void AddLanternPost(Vector3 position)
    {
        AddPropCube("Lantern Post", position + Vector3.up * 0.75f, new Vector3(0.10f, 1.5f, 0.10f), new Color(0.16f, 0.10f, 0.06f));
        AddPropCube("Lantern Arm", position + new Vector3(0.32f, 1.42f, 0), new Vector3(0.64f, 0.08f, 0.08f), new Color(0.16f, 0.10f, 0.06f));
        AddPropCube("Lantern Glow", position + new Vector3(0.68f, 1.18f, 0), new Vector3(0.34f, 0.42f, 0.34f), new Color(1.0f, 0.72f, 0.28f));
    }

    private void AddCrateStack(Vector3 position)
    {
        AddPropCube("Crate A", position + new Vector3(-0.35f, 0.25f, 0), new Vector3(0.64f, 0.5f, 0.62f), new Color(0.43f, 0.27f, 0.13f));
        AddPropCube("Crate B", position + new Vector3(0.35f, 0.25f, 0.08f), new Vector3(0.62f, 0.5f, 0.62f), new Color(0.48f, 0.31f, 0.16f));
        AddPropCube("Crate C", position + new Vector3(0.0f, 0.78f, 0.04f), new Vector3(0.58f, 0.48f, 0.58f), new Color(0.38f, 0.23f, 0.12f));
    }

    private void AddBarrelCluster(Vector3 position)
    {
        AddPropCylinder("Barrel A", position + new Vector3(-0.34f, 0.38f, 0), 0.32f, 0.75f, new Color(0.36f, 0.20f, 0.09f));
        AddPropCylinder("Barrel B", position + new Vector3(0.34f, 0.38f, 0.08f), 0.32f, 0.75f, new Color(0.40f, 0.23f, 0.10f));
    }

    private void AddFenceLine(Vector3 start, int count, float spacing, bool alongX)
    {
        for (int i = 0; i < count; i++)
        {
            Vector3 p = start + (alongX ? new Vector3(i * spacing, 0, 0) : new Vector3(0, 0, i * spacing));
            AddPropCube("Fence Post", p + Vector3.up * 0.38f, new Vector3(0.14f, 0.76f, 0.14f), new Color(0.20f, 0.12f, 0.06f));
            if (i < count - 1)
            {
                Vector3 railPos = p + (alongX ? new Vector3(spacing * 0.5f, 0.52f, 0) : new Vector3(0, 0.52f, spacing * 0.5f));
                Vector3 railScale = alongX ? new Vector3(spacing, 0.12f, 0.10f) : new Vector3(0.10f, 0.12f, spacing);
                AddPropCube("Fence Rail", railPos, railScale, new Color(0.24f, 0.15f, 0.08f));
            }
        }
    }

    private void AddForestRing()
    {
        Vector3[] points =
        {
            new Vector3(-9.7f, 0, -5.4f), new Vector3(-6.2f, 0, -6.1f), new Vector3(-2.4f, 0, -5.6f), new Vector3(2.4f, 0, -6.0f),
            new Vector3(6.2f, 0, -5.2f), new Vector3(9.2f, 0, -4.1f), new Vector3(-9.5f, 0, 4.8f), new Vector3(-5.8f, 0, 5.8f),
            new Vector3(-1.7f, 0, 5.1f), new Vector3(2.8f, 0, 5.7f), new Vector3(6.5f, 0, 4.9f), new Vector3(9.7f, 0, 3.7f)
        };
        for (int i = 0; i < points.Length; i++)
        {
            AddTree(points[i]);
        }
    }

    private void AddGabledRoof(string name, Vector3 position, Vector3 size, Color color)
    {
        Vector3 half = new Vector3(size.x * 0.5f, size.y * 0.5f, size.z * 0.5f);
        Vector3[] vertices =
        {
            new Vector3(-half.x, -half.y, -half.z), new Vector3(half.x, -half.y, -half.z), new Vector3(0, half.y, -half.z),
            new Vector3(-half.x, -half.y, half.z), new Vector3(half.x, -half.y, half.z), new Vector3(0, half.y, half.z)
        };
        int[] triangles =
        {
            0, 2, 1, 3, 4, 5,
            0, 3, 5, 0, 5, 2,
            1, 2, 5, 1, 5, 4,
            0, 1, 4, 0, 4, 3
        };
        AddMeshObject(name, position, vertices, triangles, color);
    }

    private void AddCone(string name, Vector3 position, float radius, float height, Color color)
    {
        const int segments = 18;
        Vector3[] vertices = new Vector3[segments + 2];
        vertices[0] = new Vector3(0, height * 0.5f, 0);
        vertices[1] = new Vector3(0, -height * 0.5f, 0);
        for (int i = 0; i < segments; i++)
        {
            float angle = Mathf.PI * 2.0f * i / segments;
            vertices[i + 2] = new Vector3(Mathf.Cos(angle) * radius, -height * 0.5f, Mathf.Sin(angle) * radius);
        }

        int[] triangles = new int[segments * 6];
        int t = 0;
        for (int i = 0; i < segments; i++)
        {
            int next = (i + 1) % segments;
            triangles[t++] = 0;
            triangles[t++] = i + 2;
            triangles[t++] = next + 2;
            triangles[t++] = 1;
            triangles[t++] = next + 2;
            triangles[t++] = i + 2;
        }
        AddMeshObject(name, position, vertices, triangles, color);
    }

    private GameObject AddMeshObject(string name, Vector3 position, Vector3[] vertices, int[] triangles, Color color)
    {
        GameObject obj = new GameObject(name);
        obj.transform.SetParent(propRoot, false);
        obj.transform.position = position;
        MeshFilter filter = obj.AddComponent<MeshFilter>();
        MeshRenderer renderer = obj.AddComponent<MeshRenderer>();
        Mesh mesh = new Mesh();
        mesh.name = name + " Mesh";
        mesh.vertices = vertices;
        mesh.triangles = triangles;
        mesh.RecalculateNormals();
        mesh.RecalculateBounds();
        filter.sharedMesh = mesh;
        renderer.sharedMaterial = NewStandardMaterial(color, 0.22f, 0.05f);
        spawnedAreaObjects.Add(obj);
        return obj;
    }

    private GameObject AddPropCube(string name, Vector3 position, Vector3 scale, Color color)
    {
        GameObject obj = GameObject.CreatePrimitive(PrimitiveType.Cube);
        obj.name = name;
        obj.transform.SetParent(propRoot, false);
        obj.transform.position = position;
        obj.transform.localScale = scale;
        obj.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(color, 0.2f, 0.25f);
        spawnedAreaObjects.Add(obj);
        return obj;
    }

    private GameObject AddPropCylinder(string name, Vector3 position, float radius, float height, Color color, bool trackAsAreaObject = true)
    {
        GameObject obj = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        obj.name = name;
        obj.transform.SetParent(propRoot, false);
        obj.transform.position = position;
        obj.transform.localScale = new Vector3(radius, height * 0.5f, radius);
        obj.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(color, 0.2f, 0.2f);
        if (trackAsAreaObject)
        {
            spawnedAreaObjects.Add(obj);
        }
        return obj;
    }

    private void AddTree(Vector3 position)
    {
        AddPropCylinder("Tree Trunk", position + Vector3.up * 0.65f, 0.16f, 1.3f, new Color(0.32f, 0.20f, 0.12f));
        GameObject crown = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        crown.name = "Tree Crown";
        crown.transform.SetParent(propRoot, false);
        crown.transform.position = position + Vector3.up * 1.55f;
        crown.transform.localScale = new Vector3(1.1f, 1.1f, 1.1f);
        crown.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(new Color(0.08f, 0.30f, 0.15f), 0.25f, 0.2f);
        spawnedAreaObjects.Add(crown);
    }

    private Material NewStandardMaterial(Color color, float smoothness, float metallic)
    {
        Material mat = new Material(Shader.Find("Standard"));
        mat.color = color;
        mat.SetFloat("_Glossiness", smoothness);
        mat.SetFloat("_Metallic", metallic);
        return mat;
    }

    private Material NewUnlitMaterial(Color color)
    {
        Shader shader = Shader.Find("Unlit/Texture");
        Material mat = new Material(shader != null ? shader : Shader.Find("Standard"));
        mat.color = color;
        return mat;
    }

    private RectTransform CreatePanel(Transform parent, string name, Vector2 anchorMin, Vector2 anchorMax, Vector2 offsetMin, Vector2 offsetMax, Color color)
    {
        GameObject obj = new GameObject(name);
        obj.transform.SetParent(parent, false);
        RectTransform rect = obj.AddComponent<RectTransform>();
        rect.anchorMin = anchorMin;
        rect.anchorMax = anchorMax;
        rect.offsetMin = offsetMin;
        rect.offsetMax = offsetMax;
        Image image = obj.AddComponent<Image>();
        image.color = color;
        return rect;
    }

    private RectTransform CreateGroup(Transform parent, string name, float preferredHeight)
    {
        GameObject obj = new GameObject(name);
        obj.transform.SetParent(parent, false);
        RectTransform rect = obj.AddComponent<RectTransform>();
        LayoutElement layout = obj.AddComponent<LayoutElement>();
        layout.preferredHeight = preferredHeight;
        return rect;
    }

    private Text AddBoxText(Transform parent, string name, float preferredHeight, string content, int fontSize, Font font)
    {
        RectTransform panel = CreatePanel(parent, name, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero, new Color(0.13f, 0.15f, 0.17f, 0.88f));
        LayoutElement layout = panel.gameObject.AddComponent<LayoutElement>();
        layout.preferredHeight = preferredHeight;
        Text text = AddText(panel, content, fontSize, new Color(0.88f, 0.91f, 0.92f), font, TextAnchor.UpperLeft);
        text.rectTransform.offsetMin = new Vector2(10, 8);
        text.rectTransform.offsetMax = new Vector2(-10, -8);
        text.horizontalOverflow = HorizontalWrapMode.Wrap;
        text.verticalOverflow = VerticalWrapMode.Truncate;
        return text;
    }

    private Text AddText(Transform parent, string content, int fontSize, Color color, Font font, TextAnchor anchor)
    {
        GameObject obj = new GameObject("Text");
        obj.transform.SetParent(parent, false);
        RectTransform rect = obj.AddComponent<RectTransform>();
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;
        Text text = obj.AddComponent<Text>();
        text.font = font;
        text.text = content;
        text.fontSize = fontSize;
        text.color = color;
        text.alignment = anchor;
        return text;
    }

    private Button AddButton(Transform parent, string label, Font font, UnityEngine.Events.UnityAction action)
    {
        GameObject obj = new GameObject(label);
        obj.transform.SetParent(parent, false);
        RectTransform rect = obj.AddComponent<RectTransform>();
        rect.sizeDelta = new Vector2(100, 40);
        Image image = obj.AddComponent<Image>();
        image.color = new Color(0.25f, 0.33f, 0.36f, 0.96f);
        Button button = obj.AddComponent<Button>();
        button.targetGraphic = image;
        button.onClick.AddListener(action);
        Text text = AddText(obj.transform, label, 15, new Color(0.96f, 0.95f, 0.88f), font, TextAnchor.MiddleCenter);
        text.rectTransform.offsetMin = new Vector2(4, 2);
        text.rectTransform.offsetMax = new Vector2(-4, -2);
        return button;
    }

    private InputField AddInput(Transform parent, string name, string placeholder, Font font, float preferredHeight)
    {
        GameObject obj = new GameObject(name);
        obj.transform.SetParent(parent, false);
        RectTransform rect = obj.AddComponent<RectTransform>();
        LayoutElement layout = obj.AddComponent<LayoutElement>();
        layout.preferredHeight = preferredHeight;
        Image image = obj.AddComponent<Image>();
        image.color = new Color(0.06f, 0.07f, 0.08f, 0.95f);
        InputField input = obj.AddComponent<InputField>();

        Text text = AddText(obj.transform, "", 16, Color.white, font, TextAnchor.MiddleLeft);
        text.rectTransform.offsetMin = new Vector2(10, 4);
        text.rectTransform.offsetMax = new Vector2(-10, -4);
        Text placeholderText = AddText(obj.transform, placeholder, 16, new Color(0.55f, 0.60f, 0.62f), font, TextAnchor.MiddleLeft);
        placeholderText.rectTransform.offsetMin = new Vector2(10, 4);
        placeholderText.rectTransform.offsetMax = new Vector2(-10, -4);
        input.textComponent = text;
        input.placeholder = placeholderText;
        input.onEndEdit.AddListener(value =>
        {
            if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter))
            {
                OnSubmitPressed();
            }
        });
        return input;
    }

    private Transform NewChild(Transform parent, string name)
    {
        GameObject obj = new GameObject(name);
        obj.transform.SetParent(parent, false);
        return obj.transform;
    }

    private void AddArea(string id, string displayName, string subtitle, string backgroundResource, Color groundColor)
    {
        areas[id] = new AreaDef(id, displayName, subtitle, backgroundResource, groundColor);
    }

    private void AddHotspot(string areaId, string label, string kind, string targetArea, string npcId, Vector3 position, string detail)
    {
        areas[areaId].hotspots.Add(new HotspotDef(label, kind, targetArea, npcId, position, detail));
    }

    private void AddNpcPositions(string npcId, Dictionary<string, Vector3> positions)
    {
        npcAreaPositions[npcId] = positions;
    }

    private Color RoleColor(string npcId, string role)
    {
        if (npcId.Contains("guard")) return new Color(0.78f, 0.18f, 0.16f);
        if (npcId.Contains("merchant")) return new Color(0.92f, 0.70f, 0.20f);
        if (npcId.Contains("hunter")) return new Color(0.14f, 0.62f, 0.30f);
        if (npcId.Contains("farmer")) return new Color(0.36f, 0.68f, 0.25f);
        if (npcId.Contains("blacksmith")) return new Color(0.46f, 0.44f, 0.48f);
        if (npcId.Contains("physician")) return new Color(0.38f, 0.72f, 0.84f);
        if (npcId.Contains("chief")) return new Color(0.67f, 0.42f, 0.80f);
        return new Color(0.62f, 0.64f, 0.68f);
    }

    private string DisplayName(string npcId)
    {
        return actors.ContainsKey(npcId) ? actors[npcId].displayName : npcId;
    }

    private bool IsTyping()
    {
        GameObject selected = EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;
        return selected != null && selected.GetComponent<InputField>() != null;
    }

    private string FormatNpcTooltip(Dictionary<string, object> state)
    {
        Dictionary<string, object> needs = AsDict(GetValue(state, "needs"));
        return GetString(state, "role", "") + " | " + GetString(state, "location_id", "") + "\n体力=" + GetString(needs, "energy", "?") + " 饥饿=" + GetString(needs, "hunger", "?") + " 安全=" + GetString(needs, "safety", "?");
    }

    private string FormatTask(object obj)
    {
        Dictionary<string, object> task = AsDict(obj);
        if (task.Count == 0)
        {
            return "无";
        }
        return GetString(task, "task_type", GetString(task, "action_type", "idle")) + " | target=" + GetString(task, "target_id", "-") + " | location=" + GetString(task, "location_id", "-") + " | priority=" + GetString(task, "priority", "?");
    }

    private string FormatThought(object obj)
    {
        Dictionary<string, object> thought = AsDict(obj);
        if (thought.Count == 0)
        {
            return "没有额外思考结果。";
        }
        string notes = GetString(thought, "notes", "").Trim();
        string text = "主目标：" + GetString(thought, "primary_goal", "") + "\n情绪：" + GetString(thought, "emotional_state", "") + "\n风险倾向：" + GetString(thought, "risk_attitude", "");
        if (!string.IsNullOrEmpty(notes))
        {
            text += "\n备注：" + notes;
        }
        return text;
    }

    private string FormatTickProfile(object obj)
    {
        Dictionary<string, object> profile = AsDict(obj);
        if (profile.Count == 0)
        {
            return "本轮没有 profile 数据。";
        }
        return "总耗时：" + GetString(profile, "total_ms", "?") + "ms\n执行阶段：" + GetString(profile, "execution_phase_ms", "?") + "ms\n规划阶段：" + GetString(profile, "planning_phase_ms", "?") + "ms\n计划 NPC：" + MiniJson.Serialize(GetValue(profile, "planned_npc_ids")) + "\n最慢 NPC：" + GetString(profile, "slowest_npc_id", "-");
    }

    private string FormatTickResults(object obj)
    {
        List<object> npcResults = AsList(obj);
        if (npcResults.Count == 0)
        {
            return "本轮没有 NPC 结果。";
        }

        List<string> lines = new List<string>();
        foreach (object item in npcResults)
        {
            Dictionary<string, object> result = AsDict(item);
            string npcId = GetString(result, "npc_id", "");
            lines.Add(DisplayName(npcId));
            Dictionary<string, object> execution = AsDict(GetValue(result, "execution_result"));
            lines.Add("  执行：" + FormatTask(GetValue(execution, "executed_task")));
            Dictionary<string, object> plan = AsDict(GetValue(result, "plan_result"));
            if (plan.Count > 0)
            {
                lines.Add("  规划：" + FormatTask(GetValue(plan, "selected_task")));
            }
        }
        return string.Join("\n", lines.ToArray());
    }

    private string FormatWorldUpdate(object obj)
    {
        Dictionary<string, object> update = AsDict(obj);
        if (update.Count == 0)
        {
            return "";
        }
        List<string> lines = new List<string> {"world_update"};
        AppendIfPresent(lines, update, "refreshed_resources", "resources");
        AppendIfPresent(lines, update, "matured_production_order_ids", "production_done");
        AppendIfPresent(lines, update, "moved_entity_ids", "moved");
        AppendIfPresent(lines, update, "generated_event_ids", "events");
        AppendIfPresent(lines, update, "spawned_entity_ids", "spawned");
        return string.Join("\n", lines.ToArray());
    }

    private void AppendIfPresent(List<string> lines, Dictionary<string, object> dict, string key, string label)
    {
        object value = GetValue(dict, key);
        List<object> list = AsList(value);
        if (list.Count > 0)
        {
            lines.Add(label + "=" + MiniJson.Serialize(value));
        }
    }

    private string FormatEconomySummary()
    {
        if (!economy.ContainsKey("warehouse") || !economy.ContainsKey("orders") || !economy.ContainsKey("transactions"))
        {
            return "";
        }

        List<string> warehouseParts = new List<string>();
        foreach (object itemObj in AsList(economy["warehouse"]))
        {
            if (warehouseParts.Count >= 8) break;
            Dictionary<string, object> item = AsDict(itemObj);
            warehouseParts.Add(GetString(item, "item_type", "") + " x" + GetString(item, "quantity", "0"));
        }

        List<string> orderParts = new List<string>();
        foreach (object orderObj in AsList(economy["orders"]))
        {
            if (orderParts.Count >= 4) break;
            Dictionary<string, object> order = AsDict(orderObj);
            orderParts.Add(GetString(order, "order_type", "") + "->" + GetString(order, "output_item_type", "") + " x" + GetString(order, "output_quantity", "0") + " @t" + GetString(order, "completes_at_tick", "?"));
        }

        List<string> transactionParts = new List<string>();
        foreach (object transactionObj in AsList(economy["transactions"]))
        {
            if (transactionParts.Count >= 3) break;
            Dictionary<string, object> transaction = AsDict(transactionObj);
            int delta = GetInt(transaction, "quantity_delta", 0);
            transactionParts.Add("[t" + GetString(transaction, "created_at_tick", "?") + "] " + GetString(transaction, "reason", "") + " " + (delta > 0 ? "+" : "") + delta);
        }

        return "经济状态\n仓库：" + (warehouseParts.Count > 0 ? string.Join(", ", warehouseParts.ToArray()) : "空") + "\n生产：" + (orderParts.Count > 0 ? string.Join(", ", orderParts.ToArray()) : "无待完成订单") + "\n流水：" + (transactionParts.Count > 0 ? string.Join(", ", transactionParts.ToArray()) : "暂无流水");
    }

    private static Dictionary<string, object> AsDict(object obj)
    {
        Dictionary<string, object> dict = obj as Dictionary<string, object>;
        return dict ?? new Dictionary<string, object>();
    }

    private static List<object> AsList(object obj)
    {
        List<object> list = obj as List<object>;
        return list ?? new List<object>();
    }

    private static object GetValue(Dictionary<string, object> dict, string key)
    {
        object value;
        return dict != null && dict.TryGetValue(key, out value) ? value : null;
    }

    private static string GetString(Dictionary<string, object> dict, string key, string fallback)
    {
        object value = GetValue(dict, key);
        return value == null ? fallback : Convert.ToString(value, CultureInfo.InvariantCulture);
    }

    private static int GetInt(Dictionary<string, object> dict, string key, int fallback)
    {
        object value = GetValue(dict, key);
        if (value == null)
        {
            return fallback;
        }
        if (value is long)
        {
            return (int)(long)value;
        }
        if (value is double)
        {
            return Mathf.RoundToInt((float)(double)value);
        }
        int parsed;
        return int.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), out parsed) ? parsed : fallback;
    }

    private sealed class AreaDef
    {
        public readonly string id;
        public readonly string displayName;
        public readonly string subtitle;
        public readonly string backgroundResource;
        public readonly Color groundColor;
        public readonly List<HotspotDef> hotspots = new List<HotspotDef>();

        public AreaDef(string id, string displayName, string subtitle, string backgroundResource, Color groundColor)
        {
            this.id = id;
            this.displayName = displayName;
            this.subtitle = subtitle;
            this.backgroundResource = backgroundResource;
            this.groundColor = groundColor;
        }
    }

    private sealed class HotspotDef
    {
        public readonly string label;
        public readonly string kind;
        public readonly string targetArea;
        public readonly string npcId;
        public readonly Vector3 position;
        public readonly string detail;

        public HotspotDef(string label, string kind, string targetArea, string npcId, Vector3 position, string detail)
        {
            this.label = label;
            this.kind = kind;
            this.targetArea = targetArea;
            this.npcId = npcId;
            this.position = position;
            this.detail = detail;
        }
    }

    private sealed class HotspotView
    {
        public readonly HotspotDef def;
        public readonly GameObject root;
        private readonly Renderer renderer;
        private readonly TextMesh label;

        public HotspotView(HotspotDef def, GameObject root, Renderer renderer, TextMesh label)
        {
            this.def = def;
            this.root = root;
            this.renderer = renderer;
            this.label = label;
        }

        public void SetHighlighted(bool highlighted)
        {
            renderer.material.color = highlighted ? new Color(1.0f, 0.92f, 0.36f) : new Color(0.95f, 0.72f, 0.28f);
            label.color = highlighted ? Color.white : new Color(1.0f, 0.89f, 0.48f);
        }

        public void FaceCamera(Quaternion rotation)
        {
            label.transform.rotation = rotation;
        }
    }

    private sealed class ActorView
    {
        public readonly string id;
        public string displayName;
        public string role;
        public string areaId;
        public readonly GameObject root;
        public Renderer bodyRenderer;
        public TextMesh nameLabel;
        public TextMesh speechLabel;
        public TextMesh tooltipLabel;
        private float speechTimer;

        public ActorView(string id, string displayName, string role, string areaId, GameObject root)
        {
            this.id = id;
            this.displayName = displayName;
            this.role = role;
            this.areaId = areaId;
            this.root = root;
            bodyRenderer = root.GetComponentInChildren<Renderer>();
            TextMesh[] labels = root.GetComponentsInChildren<TextMesh>();
            if (labels.Length > 0) nameLabel = labels[0];
            if (labels.Length > 1) speechLabel = labels[1];
            if (labels.Length > 2) tooltipLabel = labels[2];
        }

        public void ShowSpeech(string text)
        {
            if (speechLabel == null)
            {
                return;
            }
            speechLabel.text = text;
            speechLabel.gameObject.SetActive(!string.IsNullOrEmpty(text));
            speechTimer = string.IsNullOrEmpty(text) ? 0 : 10.0f;
        }

        public void SetHighlighted(bool highlighted)
        {
            if (tooltipLabel != null)
            {
                tooltipLabel.gameObject.SetActive(highlighted);
            }
            if (nameLabel != null)
            {
                nameLabel.color = highlighted ? Color.white : new Color(0.98f, 0.96f, 0.86f);
            }
        }

        public void FaceCamera(Quaternion rotation)
        {
            if (nameLabel != null) nameLabel.transform.rotation = rotation;
            if (speechLabel != null)
            {
                speechLabel.transform.rotation = rotation;
                if (speechTimer > 0)
                {
                    speechTimer -= Time.deltaTime;
                    if (speechTimer <= 0)
                    {
                        ShowSpeech("");
                    }
                }
            }
            if (tooltipLabel != null) tooltipLabel.transform.rotation = rotation;
        }
    }
}

public sealed class NpcSocialRpgClient
{
    private readonly MonoBehaviour owner;
    private readonly string serviceBaseUrl;

    public NpcSocialRpgClient(MonoBehaviour owner, string serviceBaseUrl)
    {
        this.owner = owner;
        this.serviceBaseUrl = serviceBaseUrl.TrimEnd('/');
    }

    public void Get(string path, Action<object> onSuccess, Action<string> onFailure)
    {
        owner.StartCoroutine(Send("GET", path, null, onSuccess, onFailure));
    }

    public void Post(string path, object body, Action<object> onSuccess, Action<string> onFailure)
    {
        owner.StartCoroutine(Send("POST", path, body, onSuccess, onFailure));
    }

    private IEnumerator Send(string method, string path, object body, Action<object> onSuccess, Action<string> onFailure)
    {
        string url = serviceBaseUrl + path;
        UnityWebRequest request = new UnityWebRequest(url, method);
        request.downloadHandler = new DownloadHandlerBuffer();
        if (body != null)
        {
            byte[] payload = Encoding.UTF8.GetBytes(MiniJson.Serialize(body));
            request.uploadHandler = new UploadHandlerRaw(payload);
            request.SetRequestHeader("Content-Type", "application/json");
        }

        yield return request.SendWebRequest();

        bool failed = request.result == UnityWebRequest.Result.ConnectionError ||
                      request.result == UnityWebRequest.Result.ProtocolError ||
                      request.result == UnityWebRequest.Result.DataProcessingError ||
                      request.responseCode < 200 ||
                      request.responseCode >= 300;
        if (failed)
        {
            string error = !string.IsNullOrEmpty(request.downloadHandler.text) ? request.downloadHandler.text : request.error;
            onFailure((int)request.responseCode + " " + error);
            request.Dispose();
            yield break;
        }

        string text = request.downloadHandler.text;
        object parsed = string.IsNullOrEmpty(text) ? new Dictionary<string, object>() : MiniJson.Deserialize(text);
        onSuccess(parsed);
        request.Dispose();
    }
}

public static class MiniJson
{
    public static object Deserialize(string json)
    {
        if (json == null)
        {
            return null;
        }
        return Parser.Parse(json);
    }

    public static string Serialize(object obj)
    {
        return Serializer.Serialize(obj);
    }

    private sealed class Parser
    {
        private readonly string json;
        private int index;

        private Parser(string json)
        {
            this.json = json;
        }

        public static object Parse(string json)
        {
            return new Parser(json).ParseValue();
        }

        private object ParseValue()
        {
            EatWhitespace();
            if (index >= json.Length)
            {
                return null;
            }

            char c = json[index];
            if (c == '{') return ParseObject();
            if (c == '[') return ParseArray();
            if (c == '"') return ParseString();
            if (c == '-' || char.IsDigit(c)) return ParseNumber();
            if (Match("true")) return true;
            if (Match("false")) return false;
            if (Match("null")) return null;
            return null;
        }

        private Dictionary<string, object> ParseObject()
        {
            Dictionary<string, object> table = new Dictionary<string, object>();
            index++;
            while (true)
            {
                EatWhitespace();
                if (index >= json.Length)
                {
                    return table;
                }
                if (json[index] == '}')
                {
                    index++;
                    return table;
                }
                string key = ParseString();
                EatWhitespace();
                if (index < json.Length && json[index] == ':')
                {
                    index++;
                }
                table[key] = ParseValue();
                EatWhitespace();
                if (index < json.Length && json[index] == ',')
                {
                    index++;
                }
            }
        }

        private List<object> ParseArray()
        {
            List<object> array = new List<object>();
            index++;
            while (true)
            {
                EatWhitespace();
                if (index >= json.Length)
                {
                    return array;
                }
                if (json[index] == ']')
                {
                    index++;
                    return array;
                }
                array.Add(ParseValue());
                EatWhitespace();
                if (index < json.Length && json[index] == ',')
                {
                    index++;
                }
            }
        }

        private string ParseString()
        {
            StringBuilder builder = new StringBuilder();
            index++;
            while (index < json.Length)
            {
                char c = json[index++];
                if (c == '"')
                {
                    break;
                }
                if (c == '\\' && index < json.Length)
                {
                    char esc = json[index++];
                    if (esc == '"') builder.Append('"');
                    else if (esc == '\\') builder.Append('\\');
                    else if (esc == '/') builder.Append('/');
                    else if (esc == 'b') builder.Append('\b');
                    else if (esc == 'f') builder.Append('\f');
                    else if (esc == 'n') builder.Append('\n');
                    else if (esc == 'r') builder.Append('\r');
                    else if (esc == 't') builder.Append('\t');
                    else if (esc == 'u' && index + 4 <= json.Length)
                    {
                        string hex = json.Substring(index, 4);
                        builder.Append((char)Convert.ToInt32(hex, 16));
                        index += 4;
                    }
                }
                else
                {
                    builder.Append(c);
                }
            }
            return builder.ToString();
        }

        private object ParseNumber()
        {
            int lastIndex = GetLastIndexOfNumber();
            string number = json.Substring(index, lastIndex - index + 1);
            index = lastIndex + 1;
            if (number.IndexOf('.') >= 0 || number.IndexOf('e') >= 0 || number.IndexOf('E') >= 0)
            {
                double parsedDouble;
                double.TryParse(number, NumberStyles.Float, CultureInfo.InvariantCulture, out parsedDouble);
                return parsedDouble;
            }
            long parsedLong;
            long.TryParse(number, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsedLong);
            return parsedLong;
        }

        private int GetLastIndexOfNumber()
        {
            int lastIndex = index;
            while (lastIndex < json.Length && "-+0123456789.eE".IndexOf(json[lastIndex]) != -1)
            {
                lastIndex++;
            }
            return lastIndex - 1;
        }

        private bool Match(string word)
        {
            if (index + word.Length > json.Length)
            {
                return false;
            }
            if (string.CompareOrdinal(json, index, word, 0, word.Length) != 0)
            {
                return false;
            }
            index += word.Length;
            return true;
        }

        private void EatWhitespace()
        {
            while (index < json.Length && char.IsWhiteSpace(json[index]))
            {
                index++;
            }
        }
    }

    private sealed class Serializer
    {
        private readonly StringBuilder builder = new StringBuilder();

        public static string Serialize(object obj)
        {
            Serializer serializer = new Serializer();
            serializer.WriteValue(obj);
            return serializer.builder.ToString();
        }

        private void WriteValue(object value)
        {
            if (value == null)
            {
                builder.Append("null");
            }
            else if (value is string)
            {
                WriteString((string)value);
            }
            else if (value is bool)
            {
                builder.Append((bool)value ? "true" : "false");
            }
            else if (value is IDictionary)
            {
                WriteObject((IDictionary)value);
            }
            else if (value is IList)
            {
                WriteArray((IList)value);
            }
            else if (value is char)
            {
                WriteString(Convert.ToString(value, CultureInfo.InvariantCulture));
            }
            else
            {
                WriteNumber(value);
            }
        }

        private void WriteObject(IDictionary obj)
        {
            bool first = true;
            builder.Append('{');
            foreach (object key in obj.Keys)
            {
                if (!first)
                {
                    builder.Append(',');
                }
                WriteString(Convert.ToString(key, CultureInfo.InvariantCulture));
                builder.Append(':');
                WriteValue(obj[key]);
                first = false;
            }
            builder.Append('}');
        }

        private void WriteArray(IList array)
        {
            builder.Append('[');
            for (int i = 0; i < array.Count; i++)
            {
                if (i > 0)
                {
                    builder.Append(',');
                }
                WriteValue(array[i]);
            }
            builder.Append(']');
        }

        private void WriteString(string str)
        {
            builder.Append('"');
            foreach (char c in str)
            {
                if (c == '"') builder.Append("\\\"");
                else if (c == '\\') builder.Append("\\\\");
                else if (c == '\b') builder.Append("\\b");
                else if (c == '\f') builder.Append("\\f");
                else if (c == '\n') builder.Append("\\n");
                else if (c == '\r') builder.Append("\\r");
                else if (c == '\t') builder.Append("\\t");
                else if (c < ' ')
                {
                    builder.Append("\\u");
                    builder.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                }
                else
                {
                    builder.Append(c);
                }
            }
            builder.Append('"');
        }

        private void WriteNumber(object number)
        {
            IFormattable formattable = number as IFormattable;
            builder.Append(formattable != null ? formattable.ToString(null, CultureInfo.InvariantCulture) : Convert.ToString(number, CultureInfo.InvariantCulture));
        }
    }
}
