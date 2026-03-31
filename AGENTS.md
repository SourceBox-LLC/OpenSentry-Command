# OpenSentry Command - Agent Documentation

##  Project Overview

OpenSentry is a cloud-hosted multi-tenant security camera system with two main components:

1. **OpenSentry Command Center** (FastAPI + React) - Cloud-hosted application with Clerk authentication
2. **OpenSentry CloudNode** (Rust) - Local application that captures USB camera video and streams to the cloud

**Project Locations:**
- Command Center: `C:\Users\Sbuss\Documents\Software Development\Projects\OpenSentry Command`
- CloudNode: `C:\Users\Sbuss\Documents\Software Development\Projects\OpenSentry-CloudNode`

---

## 🔐 Clerk Authentication Setup (CRITICAL)

### JWT V2 Token Format

OpenSentry uses **Clerk JWT V2 format** which encodes permissions differently than V1:

**V1 Format (Deprecated):**
```json
{
  "org_permissions": ["org:admin", "org:cameras:manage"]
}
```

**V2 Format (Current):**
```json
{
  "fea": "o:admin,o:cameras",
  "o": {
    "id": "org_123",
    "per": "admin,manage_cameras,view_cameras",
    "fpm": "1,3",
    "rol": "admin",
    "slg": "org-slug"
  }
}
```

### Backend Permission Decoding

The backend includes a V2 permission decoder in `backend/app/core/auth.py`:

```python
def decode_v2_permissions(claims: dict) -> list:
    """
    Decode permissions from Clerk V2 JWT format.
    V2 uses compact o claim with permission bitmap.
    """
    o_claim = claims.get("o", {})
    fea_claim = claims.get("fea", "")
    
    # Get permission names from o.per
    per_str = o_claim.get("per", "")
    permission_names = per_str.split(",") if per_str else []
    
    # Get features from fea (strip 'o:' prefix)
    features = [f[2:] if f.startswith("o:") else f for f in fea_claim.split(",")]
    
    # Get feature-permission map from o.fpm
    fpm_str = o_claim.get("fpm", "")
    fpm_values = [int(x) for x in fpm_str.split(",")] if fpm_str else []
    
    # Reconstruct full permission keys: org:{feature}:{permission}
    permissions = []
    for i, feature in enumerate(features):
        if i < len(fpm_values):
            fpm_value = fpm_values[i]
            for j, perm_name in enumerate(permission_names):
                if fpm_value & (1 << j):
                    permissions.append(f"org:{feature}:{perm_name}")
    
    return permissions
```

### Permission Key Format

Your Clerk permissions must match this format in the code:

```python
@property
def is_admin(self) -> bool:
    return self.has_permission("org:admin:admin") or self.has_permission(
        "org:cameras:manage_cameras"
    )

@property
def can_view_cameras(self) -> bool:
    return self.has_permission("org:cameras:view_cameras") or self.is_admin
```

### Clerk Dashboard Configuration

#### 1. Create Features and Permissions

Go to **Configure** → **Organizations** → **Roles & Permissions**:

**Features to create:**
- `admin` (Key: `admin`) - Full admin access
- `cameras` (Key: `cameras`) - Camera management permissions

**Permissions under `admin` feature:**
- `Admin` (Key: `admin`) → `org:admin:admin`

**Permissions under `cameras` feature:**
- `Manage Cameras` (Key: `manage_cameras`) → `org:cameras:manage_cameras`
- `View Cameras` (Key: `view_cameras`) → `org:cameras:view_cameras`

#### 2. Assign Permissions to Roles

Go to **All roles** tab → Edit **Admin** role:
- ✅ Check `org:admin:admin`
- ✅ Check `org:cameras:manage_cameras`
- ✅ Check `org:cameras:view_cameras`

#### 3. Configure Role Set

Go to **Role Sets** tab:
- Ensure **Default role set** includes the **Admin** role
- Make sure the role set is active for your organization

#### 4. JWT Template Configuration

Go to **Configure** → **JWT Templates** → **default**:

**Claims field:** Set to `{}` (empty object)
- This allows Clerk to use default V2 claims
- Do NOT add custom `org_permissions` claims - V2 handles this automatically

**Important:** After changing JWT template settings:
1. Save the template
2. Sign out of your app completely
3. Sign back in to get a fresh JWT token

#### 5. Assign User to Admin Role

Go to **Organizations** → Select your organization → Members:
- Find your user
- Set role to **Admin** (not just `org:admin`, but your custom Admin role)

---

## 🏗️ Architecture

### Frontend → Backend Communication

```
Browser (localhost:5173) → Backend (localhost:8000) ← ngrok ← Rust Camera Nodes (external)
```

**Key Points:**
- Frontend talks directly to backend on same machine (no CORS issues)
- ngrok is ONLY for external Rust camera nodes to reach the backend
- `VITE_API_URL` should be `http://localhost:8000` (not ngrok URL)

### CORS Configuration

Backend CORS in `backend/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://ulises-nonruinable-shapelessly.ngrok-free.dev",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Important:** Cannot use `allow_origins=["*"]` with `allow_credentials=True` - violates CORS spec.

---

## 📁 Key Files

### Backend

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app, CORS middleware |
| `backend/app/core/auth.py` | Clerk authentication, V2 permission decoder |
| `backend/app/core/clerk.py` | Clerk client initialization |
| `backend/app/core/config.py` | Configuration from environment |
| `backend/app/api/nodes.py` | Node CRUD endpoints |
| `backend/app/models/models.py` | SQLAlchemy models (CameraNode, Camera) |
| `backend/app/schemas/schemas.py` | Pydantic schemas |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/components/AddNodeModal.jsx` | Node creation modal (uses onClick, not form submit) |
| `frontend/src/pages/SettingsPage.jsx` | Settings page with node management |
| `frontend/src/services/api.js` | API client with auth token handling |
| `frontend/src/index.css` | Modal and node list styles |

---

## 🔧 Development Notes

### React 19 Form Handling

**Problem:** React 19's form handling can cause full page refreshes with traditional `onSubmit`.

**Solution:** Use `onClick` handler instead of form submission:

```jsx
function AddNodeModal({ isOpen, onClose, onCreate }) {
  const [loading, setLoading] = useState(false)
  const inputRef = useRef(null)

  async function handleCreateClick() {
    const name = inputRef.current?.value
    setLoading(true)
    try {
      const result = await onCreate(name.trim())
      // Handle result
    } finally {
      setLoading(false)
    }
  }

  return (
    <input ref={inputRef} type="text" />
    <button onClick={handleCreateClick} disabled={loading}>
      Create Node
    </button>
  )
}
```

**Avoid:**
- `<form onSubmit={...}>` patterns in React 19
- Using `action` prop without proper React 19 server actions setup

### Authentication Debugging

Add logging to `backend/app/core/auth.py`:

```python
print(f"[Auth] JWT claims: {list(claims.keys())}")
print(f"[Auth] V2 debug - fea: {claims.get('fea')}")
print(f"[Auth] V2 debug - o claim: {claims.get('o')}")
print(f"[Auth] Decoded permissions: {org_permissions}")
```

Expected output after successful auth:
```
[Auth] V2 debug - fea: o:admin,o:cameras
[Auth] V2 debug - o claim: {'fpm': '1,6', 'per': 'admin,manage_cameras,view_cameras'}
[Auth] Decoded permissions: ['org:admin:admin', 'org:cameras:manage_cameras', 'org:cameras:view_cameras']
```

### Common Issues

#### 403 Forbidden on Node Creation

**Cause:** Permissions not decoded from V2 JWT token.

**Fix:**
1. Verify JWT template claims is `{}`
2. Sign out and back in
3. Check backend logs for `permissions=None` vs actual array
4. Verify V2 decoder is working

#### Page Refresh on Form Submit

**Cause:** React 19 form handling issue.

**Fix:**
1. Use `onClick` instead of `onSubmit`
2. Or ensure `e.preventDefault()` is called synchronously
3. Avoid `action` prop unless using React 19 server actions

#### CORS Errors

**Cause:** Using ngrok URL for frontend→backend communication.

**Fix:**
1. Set `VITE_API_URL=http://localhost:8000`
2. Only use ngrok URL for external Rust nodes
3. Verify CORS origins in `backend/app/main.py`

---

##  Node Creation Flow

### Steps

1. User clicks "Add Node" in Settings page
2. Modal opens with node name input
3. User enters name and clicks "Create Node"
4. Frontend calls `POST /api/nodes` with auth token
5. Backend:
   - Validates Clerk JWT token
   - Decodes V2 permissions
   - Checks `require_admin` permission
   - Generates `node_id` and `api_key`
   - Saves to database with hashed API key
6. Response includes:
   - `node_id` (e.g., `cf394d69`)
   - `api_key` (e.g., `f3eda4fd-7810-4577-94a8-290fbb6d9523`)
   - Warning: "Store this API key securely. It cannot be retrieved again."
7. Modal shows credentials with copy buttons
8. User copies credentials for Rust node configuration

### API Endpoints

```
POST /api/nodes
Headers: Authorization: Bearer <jwt_token>
Body: { "name": "Home" }

Response: {
  "success": true,
  "node_id": "cf394d69",
  "name": "Home",
  "api_key": "f3eda4fd-7810-4577-94a8-290fbb6d9523",
  "warning": "Store this API key securely..."
}
```

### Rust Node Usage

The generated credentials are used with the Rust CloudNode:

```bash
cargo run -- \
  --node-id cf394d69 \
  --api-key f3eda4fd-7810-4577-94a8-290fbb6d9523 \
  --api-url https://ulises-nonruinable-shapelessly.ngrok-free.dev
```

---

## 📝 Testing Checklist

### Authentication

- [ ] Sign out and sign back in after JWT template changes
- [ ] Check backend logs for decoded permissions
- [ ] Verify `org:admin:admin` permission is present
- [ ] Test with non-admin user (should get 403)

### Node Creation

- [ ] Modal opens without errors
- [ ] Form submission doesn't refresh page
- [ ] API call includes auth token
- [ ] Node appears in database
- [ ] Node appears in Settings page list
- [ ] API key is shown only once
- [ ] Copy buttons work

### Node Registration (Rust)

- [ ] Rust node can register with API key
- [ ] Node status updates to "online"
- [ ] Heartbeat endpoint works
- [ ] Cameras are auto-created from registration

---

## 🔐 Security Best Practices

1. **API Keys:** Hash with SHA256 before storing in database
2. **JWT Tokens:** Validate with Clerk's JWKS endpoint
3. **CORS:** Explicit origins only, never `*` with credentials
4. **Permissions:** Always check on backend, never trust frontend
5. **ngrok:** Use only for external node access, not frontend

---

## 📚 References

- Clerk V2 JWT Format: https://clerk.com/docs/guides/sessions/session-tokens
- Clerk Organizations: https://clerk.com/docs/guides/organizations/overview
- Clerk Permissions: https://clerk.com/docs/guides/organizations/control-access/roles-and-permissions
- React 19 Forms: https://react.dev/reference/react-dom/components/form

---

**Last Updated:** March 30, 2026  
**Status:** ✅ Node creation flow fully functional with Clerk V2 authentication
