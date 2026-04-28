using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class VillageWatchSceneBuilder
{
    private const string ScenePath = "Assets/Scenes/VillageWatch3D.unity";

    private static readonly Dictionary<string, Color> AreaColors = new Dictionary<string, Color>
    {
        {"village_entrance", new Color(0.31f, 0.43f, 0.31f)},
        {"village_square", new Color(0.32f, 0.40f, 0.36f)},
        {"village_market", new Color(0.43f, 0.35f, 0.25f)},
        {"hunting_forest", new Color(0.16f, 0.34f, 0.20f)},
        {"village_rest_area", new Color(0.30f, 0.35f, 0.31f)}
    };

    private static readonly Dictionary<string, string> AreaNames = new Dictionary<string, string>
    {
        {"village_entrance", "Village Entrance"},
        {"village_square", "Village Square"},
        {"village_market", "Village Market"},
        {"hunting_forest", "Hunting Forest"},
        {"village_rest_area", "Rest Area"}
    };

    private static readonly Dictionary<string, string> Backgrounds = new Dictionary<string, string>
    {
        {"village_entrance", "Assets/Resources/Backgrounds/village_entrance.png"},
        {"village_square", "Assets/Resources/Backgrounds/village_square.png"},
        {"village_market", "Assets/Resources/Backgrounds/village_market.png"},
        {"hunting_forest", "Assets/Resources/Backgrounds/hunting_forest.png"},
        {"village_rest_area", "Assets/Resources/Backgrounds/village_rest_area.png"}
    };

    [MenuItem("NPC Social RPG/Build Migrated Unity 3D Scene")]
    public static void BuildScene()
    {
        ConfigureHighQualityTextureImporters();

        Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.ExponentialSquared;
        RenderSettings.fogDensity = 0.012f;
        RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.54f, 0.58f, 0.61f);
        RenderSettings.ambientEquatorColor = new Color(0.38f, 0.34f, 0.30f);
        RenderSettings.ambientGroundColor = new Color(0.20f, 0.18f, 0.15f);

        GameObject controller = new GameObject("VillageWatch3D");
        controller.AddComponent<VillageWatch3D>();

        Transform previewRoot = new GameObject("Baked Unity 3D Migration Preview").transform;
        Transform areasRoot = NewChild(previewRoot, "Five Migrated Areas");
        Transform actorsRoot = NewChild(previewRoot, "NPCs And Player");
        Transform uiRoot = NewChild(previewRoot, "Baked UI Preview");

        BuildLightingAndCamera(previewRoot);

        BuildArea(areasRoot, "village_entrance", new Vector3(-28, 0, 0));
        BuildArea(areasRoot, "village_square", new Vector3(-14, 0, 0));
        BuildArea(areasRoot, "village_market", new Vector3(0, 0, 0));
        BuildArea(areasRoot, "hunting_forest", new Vector3(14, 0, 0));
        BuildArea(areasRoot, "village_rest_area", new Vector3(28, 0, 0));

        BuildActors(actorsRoot);
        BuildBakedUi(uiRoot);
        BuildSceneGuide(previewRoot);

        EditorSceneManager.SaveScene(scene, ScenePath);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log("Built migrated Unity 3D scene at " + ScenePath);
    }

    [MenuItem("NPC Social RPG/Capture Migrated Unity 3D Preview")]
    public static void CapturePreview()
    {
        EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
        Camera camera = Object.FindObjectOfType<Camera>();
        if (camera == null)
        {
            Debug.LogError("No camera found in " + ScenePath);
            return;
        }

        camera.transform.position = new Vector3(0, 18.0f, -23.0f);
        camera.transform.LookAt(new Vector3(0, 0.8f, 0), Vector3.up);
        camera.orthographic = false;
        camera.fieldOfView = 50.0f;

        RenderTexture target = new RenderTexture(1920, 1080, 24);
        Texture2D image = new Texture2D(1920, 1080, TextureFormat.RGB24, false);
        RenderTexture previous = RenderTexture.active;
        camera.targetTexture = target;
        RenderTexture.active = target;
        camera.Render();
        image.ReadPixels(new Rect(0, 0, 1920, 1080), 0, 0);
        image.Apply();
        camera.targetTexture = null;
        RenderTexture.active = previous;

        string outputPath = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "migration_preview.png"));
        File.WriteAllBytes(outputPath, image.EncodeToPNG());
        Object.DestroyImmediate(image);
        Object.DestroyImmediate(target);
        Debug.Log("Captured migrated Unity 3D preview at " + outputPath);
    }

    private static void BuildLightingAndCamera(Transform root)
    {
        Camera camera = new GameObject("Main Camera").AddComponent<Camera>();
        camera.tag = "MainCamera";
        camera.transform.SetParent(root, false);
        camera.transform.position = new Vector3(0, 18.0f, -23.0f);
        camera.transform.LookAt(new Vector3(0, 0.8f, 0), Vector3.up);
        camera.orthographic = false;
        camera.fieldOfView = 50.0f;
        camera.clearFlags = CameraClearFlags.SolidColor;
        camera.backgroundColor = new Color(0.34f, 0.45f, 0.52f);

        Light sun = new GameObject("Sun - migrated directional light").AddComponent<Light>();
        sun.transform.SetParent(root, false);
        sun.type = LightType.Directional;
        sun.intensity = 1.25f;
        sun.transform.rotation = Quaternion.Euler(52, -34, 0);
    }

    private static void BuildArea(Transform parent, string areaId, Vector3 offset)
    {
        Transform area = NewChild(parent, AreaNames[areaId] + " / " + areaId);
        area.position = offset;

        GameObject ground = CreatePrimitive(area, PrimitiveType.Cube, "Ground", new Vector3(0, -0.08f, 0), new Vector3(11.6f, 0.16f, 8.2f), AreaColors[areaId]);
        ground.isStatic = true;

        Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(Backgrounds[areaId]);
        GameObject backdrop = CreatePrimitive(area, PrimitiveType.Quad, "Migrated 2D backdrop billboard", new Vector3(0, 3.7f, 4.25f), new Vector3(10.8f, 6.1f, 1), Color.white);
        backdrop.transform.rotation = Quaternion.Euler(0, 180, 0);
        Material backdropMat = NewUnlitMaterial(Color.white);
        backdropMat.mainTexture = texture;
        if (texture != null)
        {
            texture.filterMode = FilterMode.Trilinear;
            texture.anisoLevel = 8;
        }
        backdrop.GetComponent<Renderer>().sharedMaterial = backdropMat;

        AddAreaProps(area, areaId);
        AddHotspots(area, areaId);
        AddLabel(area, AreaNames[areaId], new Vector3(0, 0.08f, -4.65f), 52, new Color(1.0f, 0.92f, 0.66f));
    }

    private static void AddAreaProps(Transform area, string areaId)
    {
        CreatePrimitive(area, PrimitiveType.Cube, "Main walkable path", new Vector3(0, 0.02f, 0.6f), new Vector3(8.8f, 0.08f, 1.15f), new Color(0.43f, 0.38f, 0.30f));

        if (areaId == "village_entrance")
        {
            CreatePrimitive(area, PrimitiveType.Cube, "Gate wall", new Vector3(0, 0.7f, 1.7f), new Vector3(4.4f, 1.4f, 0.45f), new Color(0.55f, 0.52f, 0.46f));
            AddPreviewTower(area, new Vector3(2.8f, 0, 2.0f));
            AddPreviewHouse(area, "Gatekeeper Lodge", new Vector3(-3.0f, 0, 1.5f), new Color(0.50f, 0.38f, 0.25f), new Color(0.34f, 0.12f, 0.10f));
            CreatePrimitive(area, PrimitiveType.Cylinder, "Water mill marker", new Vector3(4.2f, 0.35f, 0.3f), new Vector3(0.8f, 0.25f, 0.8f), new Color(0.24f, 0.44f, 0.55f));
        }
        else if (areaId == "village_square")
        {
            CreatePrimitive(area, PrimitiveType.Cylinder, "Central fountain", new Vector3(0, 0.32f, 0.0f), new Vector3(1.2f, 0.35f, 1.2f), new Color(0.43f, 0.58f, 0.64f));
            AddPreviewHouse(area, "Notice Hall", new Vector3(1.2f, 0, 2.4f), new Color(0.58f, 0.46f, 0.33f), new Color(0.28f, 0.12f, 0.08f));
            AddPreviewHouse(area, "Guild House", new Vector3(-3.3f, 0, 1.8f), new Color(0.54f, 0.42f, 0.31f), new Color(0.24f, 0.18f, 0.14f));
        }
        else if (areaId == "village_market")
        {
            AddPreviewMarketStall(area, new Vector3(1.0f, 0, 1.1f), new Color(0.72f, 0.23f, 0.16f));
            AddPreviewMarketStall(area, new Vector3(3.2f, 0, -0.4f), new Color(0.18f, 0.36f, 0.66f));
            CreatePrimitive(area, PrimitiveType.Cube, "Supply crates", new Vector3(-1.8f, 0.35f, -2.3f), new Vector3(1.9f, 0.7f, 1.2f), new Color(0.50f, 0.35f, 0.20f));
            AddPreviewHouse(area, "Apothecary", new Vector3(-3.5f, 0, 1.5f), new Color(0.48f, 0.42f, 0.34f), new Color(0.16f, 0.25f, 0.22f));
        }
        else if (areaId == "hunting_forest")
        {
            for (int i = 0; i < 12; i++)
            {
                float x = -4.8f + (i % 4) * 3.2f;
                float z = -3.2f + (i / 4) * 3.1f;
                AddTree(area, new Vector3(x, 0, z));
            }
            CreatePrimitive(area, PrimitiveType.Cube, "Hunter camp", new Vector3(2.2f, 0.35f, 1.8f), new Vector3(1.8f, 0.7f, 1.1f), new Color(0.37f, 0.24f, 0.14f));
            CreatePrimitive(area, PrimitiveType.Cube, "Runestone", new Vector3(-2.4f, 0.75f, 0.4f), new Vector3(0.5f, 1.5f, 0.24f), new Color(0.30f, 0.33f, 0.34f));
        }
        else if (areaId == "village_rest_area")
        {
            AddPreviewHouse(area, "Rest Cabin", new Vector3(2.9f, 0, 1.8f), new Color(0.52f, 0.38f, 0.25f), new Color(0.24f, 0.12f, 0.08f));
            AddPreviewHouse(area, "Healer Hut", new Vector3(-2.5f, 0, 1.2f), new Color(0.43f, 0.47f, 0.38f), new Color(0.18f, 0.30f, 0.18f));
            CreatePrimitive(area, PrimitiveType.Cylinder, "Campfire", new Vector3(0, 0.2f, -1.8f), new Vector3(0.55f, 0.28f, 0.55f), new Color(0.95f, 0.38f, 0.12f));
        }
    }

    private static void AddPreviewHouse(Transform area, string name, Vector3 position, Color wallColor, Color roofColor)
    {
        CreatePrimitive(area, PrimitiveType.Cube, name + " stone plinth", position + new Vector3(0, 0.13f, 0), new Vector3(2.7f, 0.26f, 1.8f), new Color(0.34f, 0.33f, 0.30f));
        CreatePrimitive(area, PrimitiveType.Cube, name + " timber body", position + new Vector3(0, 0.83f, 0), new Vector3(2.45f, 1.3f, 1.55f), wallColor);
        CreatePrimitive(area, PrimitiveType.Cube, name + " steep roof", position + new Vector3(0, 1.65f, 0), new Vector3(2.9f, 0.45f, 1.95f), roofColor);
        CreatePrimitive(area, PrimitiveType.Cube, name + " door", position + new Vector3(0, 0.55f, -0.82f), new Vector3(0.5f, 0.85f, 0.08f), new Color(0.20f, 0.12f, 0.07f));
        CreatePrimitive(area, PrimitiveType.Cube, name + " warm window", position + new Vector3(-0.72f, 0.92f, -0.84f), new Vector3(0.34f, 0.25f, 0.06f), new Color(0.95f, 0.73f, 0.35f));
    }

    private static void AddPreviewTower(Transform area, Vector3 position)
    {
        CreatePrimitive(area, PrimitiveType.Cylinder, "Watchtower footing", position + Vector3.up * 0.25f, new Vector3(0.8f, 0.25f, 0.8f), new Color(0.38f, 0.36f, 0.32f));
        CreatePrimitive(area, PrimitiveType.Cube, "Watchtower shaft", position + Vector3.up * 1.6f, new Vector3(1.15f, 2.8f, 1.15f), new Color(0.34f, 0.22f, 0.13f));
        CreatePrimitive(area, PrimitiveType.Cube, "Watchtower platform", position + Vector3.up * 3.0f, new Vector3(1.8f, 0.24f, 1.8f), new Color(0.26f, 0.16f, 0.09f));
        CreatePrimitive(area, PrimitiveType.Cylinder, "Watchtower roof", position + Vector3.up * 3.55f, new Vector3(1.05f, 0.45f, 1.05f), new Color(0.23f, 0.09f, 0.08f));
    }

    private static void AddPreviewMarketStall(Transform area, Vector3 position, Color clothColor)
    {
        CreatePrimitive(area, PrimitiveType.Cube, "Market stall table", position + Vector3.up * 0.42f, new Vector3(2.0f, 0.2f, 1.05f), new Color(0.34f, 0.20f, 0.10f));
        CreatePrimitive(area, PrimitiveType.Cube, "Market stall cloth", position + Vector3.up * 1.28f, new Vector3(2.35f, 0.16f, 1.35f), clothColor);
        CreatePrimitive(area, PrimitiveType.Cube, "Market stall crates", position + new Vector3(1.35f, 0.35f, 0.12f), new Vector3(0.82f, 0.7f, 0.72f), new Color(0.43f, 0.27f, 0.13f));
    }

    private static void AddHotspots(Transform area, string areaId)
    {
        if (areaId == "village_entrance")
        {
            AddHotspot(area, "To Square", new Vector3(-0.7f, 0.1f, 2.5f));
            AddHotspot(area, "Watch Tower", new Vector3(2.8f, 0.1f, 2.6f));
            AddHotspot(area, "Water Mill", new Vector3(4.3f, 0.1f, 0.5f));
        }
        else if (areaId == "village_square")
        {
            AddHotspot(area, "To Market", new Vector3(3.9f, 0.1f, 0.6f));
            AddHotspot(area, "Fountain", new Vector3(0, 0.1f, 0));
            AddHotspot(area, "Notice Hall", new Vector3(1.2f, 0.1f, 2.6f));
        }
        else if (areaId == "village_market")
        {
            AddHotspot(area, "Merchant Stall", new Vector3(1.0f, 0.1f, 1.2f));
            AddHotspot(area, "Supply Crates", new Vector3(-1.8f, 0.1f, -2.5f));
            AddHotspot(area, "To Forest", new Vector3(4.2f, 0.1f, 2.5f));
        }
        else if (areaId == "hunting_forest")
        {
            AddHotspot(area, "Hunter Camp", new Vector3(2.2f, 0.1f, 1.8f));
            AddHotspot(area, "Animal Trail", new Vector3(0, 0.1f, -1.7f));
            AddHotspot(area, "Back To Market", new Vector3(4.5f, 0.1f, 0));
        }
        else if (areaId == "village_rest_area")
        {
            AddHotspot(area, "Rest Cabin", new Vector3(2.9f, 0.1f, 1.8f));
            AddHotspot(area, "Campfire", new Vector3(0, 0.1f, -1.8f));
            AddHotspot(area, "To Forest", new Vector3(3.7f, 0.1f, 2.8f));
        }
    }

    private static void BuildActors(Transform parent)
    {
        AddActor(parent, "Player", "player_001", new Vector3(-28, 0, -2.2f), new Color(0.18f, 0.42f, 0.95f));
        AddActor(parent, "Darin Guard", "npc_guard_001", new Vector3(-25.7f, 0, 0.5f), new Color(0.78f, 0.18f, 0.16f));
        AddActor(parent, "Mira Merchant", "npc_merchant_001", new Vector3(1.0f, 0, 1.1f), new Color(0.92f, 0.70f, 0.20f));
        AddActor(parent, "Aren Hunter", "npc_hunter_001", new Vector3(16.4f, 0, 1.6f), new Color(0.14f, 0.62f, 0.30f));
        AddActor(parent, "Lysa Farmer", "npc_farmer_001", new Vector3(-15.3f, 0, -1.1f), new Color(0.36f, 0.68f, 0.25f));
        AddActor(parent, "Bran Blacksmith", "npc_blacksmith_001", new Vector3(-14.0f, 0, -1.2f), new Color(0.46f, 0.44f, 0.48f));
        AddActor(parent, "Sena Physician", "npc_physician_001", new Vector3(-12.7f, 0, -1.2f), new Color(0.38f, 0.72f, 0.84f));
        AddActor(parent, "Orlen Chief", "npc_village_chief_001", new Vector3(-11.4f, 0, -1.0f), new Color(0.67f, 0.42f, 0.80f));
        AddActor(parent, "Wolf Entity", "monster_wolf_001", new Vector3(17.8f, 0, -0.8f), new Color(0.84f, 0.22f, 0.16f));
    }

    private static void BuildBakedUi(Transform parent)
    {
        Canvas canvas = new GameObject("Baked HUD Layout").AddComponent<Canvas>();
        canvas.transform.SetParent(parent, false);
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        CanvasScaler scaler = canvas.gameObject.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        canvas.gameObject.AddComponent<GraphicRaycaster>();

        if (Object.FindObjectOfType<EventSystem>() == null)
        {
            GameObject eventSystem = new GameObject("EventSystem");
            eventSystem.transform.SetParent(parent, false);
            eventSystem.AddComponent<EventSystem>();
            eventSystem.AddComponent<StandaloneInputModule>();
        }

        Font font = CreateReadableFont();
        RectTransform sidebar = CreateUiPanel(canvas.transform, "Runtime control sidebar", new Vector2(1, 0), new Vector2(1, 1), new Vector2(-548, 16), new Vector2(-16, -16), new Color(0.08f, 0.095f, 0.11f, 0.96f));
        VerticalLayoutGroup layout = sidebar.gameObject.AddComponent<VerticalLayoutGroup>();
        layout.padding = new RectOffset(14, 14, 14, 14);
        layout.spacing = 8;
        layout.childControlWidth = true;
        layout.childControlHeight = true;
        layout.childForceExpandWidth = true;
        layout.childForceExpandHeight = false;

        AddUiBox(sidebar, "Village Watch 3D\nTick 0\nStatus: waiting for backend", 92, 22, font);
        AddUiBox(sidebar, "Nearby NPC: none\nSelected: none", 58, 16, font);
        AddUiBox(sidebar, "Dialogue history will appear here.\nInput field, dialogue buttons, and event buttons are active in Play Mode.", 132, 15, font);
        AddUiBox(sidebar, "Buttons: Talk/E  Suspicious/O  Plan/P  Reset/R\nButtons: Tick/T  Auto Tick  Monster  Shortage  Theft", 92, 15, font);
        AddUiBox(sidebar, "Thought and planning output", 128, 15, font);
        AddUiBox(sidebar, "Task execution output", 142, 15, font);
        AddUiBox(sidebar, "World event log", 110, 15, font);
        AddUiBox(sidebar, "Buildings, hotspots, resources, economy, and entities", 138, 15, font);
    }

    private static void BuildSceneGuide(Transform root)
    {
        AddLabel(root, "Godot 2D -> Unity 3D Full Migration\nFive areas, seven NPCs, hotspots, events, dialogue UI, resources, economy, and backend sync are migrated into Unity.", new Vector3(0, 0.25f, -7.2f), 64, new Color(0.98f, 0.95f, 0.82f));
    }

    private static void AddActor(Transform parent, string label, string id, Vector3 position, Color color)
    {
        Transform actor = NewChild(parent, label + " / " + id);
        actor.position = position;
        CreatePrimitive(actor, PrimitiveType.Cylinder, "shadow", new Vector3(0, 0.03f, 0), new Vector3(0.8f, 0.03f, 0.8f), new Color(0, 0, 0, 0.32f));
        CreatePrimitive(actor, PrimitiveType.Capsule, "body", new Vector3(0, 0.75f, 0), new Vector3(0.72f, 0.9f, 0.72f), color);
        AddLabel(actor, label, new Vector3(0, 1.9f, 0), 42, new Color(0.98f, 0.96f, 0.86f));
    }

    private static void AddHotspot(Transform parent, string label, Vector3 position)
    {
        Transform hotspot = NewChild(parent, "Hotspot - " + label);
        hotspot.localPosition = position;
        CreatePrimitive(hotspot, PrimitiveType.Cylinder, "marker", new Vector3(0, 0.06f, 0), new Vector3(0.45f, 0.07f, 0.45f), new Color(0.95f, 0.72f, 0.28f));
        AddLabel(hotspot, label, new Vector3(0, 0.55f, 0), 34, new Color(1.0f, 0.90f, 0.48f));
    }

    private static void AddTree(Transform parent, Vector3 position)
    {
        CreatePrimitive(parent, PrimitiveType.Cylinder, "Tree trunk", position + Vector3.up * 0.65f, new Vector3(0.16f, 0.65f, 0.16f), new Color(0.32f, 0.20f, 0.12f));
        CreatePrimitive(parent, PrimitiveType.Capsule, "Tree crown", position + Vector3.up * 1.55f, new Vector3(1.1f, 1.15f, 1.1f), new Color(0.08f, 0.30f, 0.15f));
    }

    private static GameObject CreatePrimitive(Transform parent, PrimitiveType type, string name, Vector3 localPosition, Vector3 localScale, Color color)
    {
        GameObject obj = GameObject.CreatePrimitive(type);
        obj.name = name;
        obj.transform.SetParent(parent, false);
        obj.transform.localPosition = localPosition;
        obj.transform.localScale = localScale;
        obj.GetComponent<Renderer>().sharedMaterial = NewStandardMaterial(color);
        return obj;
    }

    private static TextMesh AddLabel(Transform parent, string text, Vector3 localPosition, int fontSize, Color color)
    {
        GameObject labelObject = new GameObject("Label - " + FirstLine(text));
        labelObject.transform.SetParent(parent, false);
        labelObject.transform.localPosition = localPosition;
        labelObject.transform.rotation = Quaternion.Euler(58, 0, 0);
        TextMesh label = labelObject.AddComponent<TextMesh>();
        label.text = text;
        label.anchor = TextAnchor.MiddleCenter;
        label.alignment = TextAlignment.Center;
        label.characterSize = 0.09f;
        label.fontSize = fontSize;
        label.color = color;
        return label;
    }

    private static RectTransform CreateUiPanel(Transform parent, string name, Vector2 anchorMin, Vector2 anchorMax, Vector2 offsetMin, Vector2 offsetMax, Color color)
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

    private static void AddUiBox(Transform parent, string content, float preferredHeight, int fontSize, Font font)
    {
        RectTransform panel = CreateUiPanel(parent, "UI Box", Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero, new Color(0.13f, 0.15f, 0.17f, 0.88f));
        LayoutElement layout = panel.gameObject.AddComponent<LayoutElement>();
        layout.preferredHeight = preferredHeight;

        GameObject textObject = new GameObject("Text");
        textObject.transform.SetParent(panel, false);
        RectTransform rect = textObject.AddComponent<RectTransform>();
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = new Vector2(10, 8);
        rect.offsetMax = new Vector2(-10, -8);
        Text text = textObject.AddComponent<Text>();
        text.font = font;
        text.text = content;
        text.fontSize = fontSize;
        text.color = new Color(0.88f, 0.91f, 0.92f);
        text.alignment = TextAnchor.UpperLeft;
        text.horizontalOverflow = HorizontalWrapMode.Wrap;
        text.verticalOverflow = VerticalWrapMode.Truncate;
    }

    private static Transform NewChild(Transform parent, string name)
    {
        GameObject obj = new GameObject(name);
        obj.transform.SetParent(parent, false);
        return obj.transform;
    }

    private static Material NewStandardMaterial(Color color)
    {
        Material material = new Material(Shader.Find("Standard"));
        material.color = color;
        material.SetFloat("_Glossiness", 0.22f);
        material.SetFloat("_Metallic", 0.05f);
        return material;
    }

    private static Material NewUnlitMaterial(Color color)
    {
        Material material = new Material(Shader.Find("Unlit/Texture"));
        material.color = color;
        return material;
    }

    private static void ConfigureHighQualityTextureImporters()
    {
        foreach (string texturePath in Backgrounds.Values)
        {
            TextureImporter importer = AssetImporter.GetAtPath(texturePath) as TextureImporter;
            if (importer == null)
            {
                continue;
            }

            bool dirty = false;
            if (importer.mipmapEnabled)
            {
                importer.mipmapEnabled = false;
                dirty = true;
            }
            if (importer.textureCompression != TextureImporterCompression.Uncompressed)
            {
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                dirty = true;
            }
            if (importer.maxTextureSize < 4096)
            {
                importer.maxTextureSize = 4096;
                dirty = true;
            }
            if (importer.filterMode != FilterMode.Trilinear)
            {
                importer.filterMode = FilterMode.Trilinear;
                dirty = true;
            }
            if (importer.anisoLevel < 8)
            {
                importer.anisoLevel = 8;
                dirty = true;
            }

            TextureImporterPlatformSettings defaultSettings = importer.GetDefaultPlatformTextureSettings();
            if (defaultSettings.maxTextureSize < 4096 || defaultSettings.textureCompression != TextureImporterCompression.Uncompressed)
            {
                defaultSettings.maxTextureSize = 4096;
                defaultSettings.textureCompression = TextureImporterCompression.Uncompressed;
                importer.SetPlatformTextureSettings(defaultSettings);
                dirty = true;
            }

            if (dirty)
            {
                importer.SaveAndReimport();
            }
        }
    }

    private static Font CreateReadableFont()
    {
        Font font = Font.CreateDynamicFontFromOSFont(new[] {"Microsoft YaHei", "SimHei", "Arial"}, 16);
        return font != null ? font : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
    }

    private static string FirstLine(string text)
    {
        int index = text.IndexOf('\n');
        return index >= 0 ? text.Substring(0, index) : text;
    }
}
