import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { MessageKey } from "../i18n/messages";
import {
  type ApiProblem,
  createIamUser,
  deleteIamUser,
  type IamGroup,
  type IamUser,
  listManagementResources,
  ManagementApiError,
  setIamUserPassword,
  updateIamUser,
} from "../lib/managementApi";

interface UserManagementPanelProps {
  areaDescription: string;
  areaTitle: string;
  moduleName: string;
}

interface UserDraft {
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  group_ids: number[];
}

const emptyDraft: UserDraft = {
  email: "",
  first_name: "",
  last_name: "",
  is_active: true,
  is_staff: false,
  is_superuser: false,
  group_ids: [],
};

function reconnectUrl() {
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/oauth2/start?rd=${encodeURIComponent(returnTo)}`;
}

function draftFromUser(user: IamUser): UserDraft {
  return {
    email: user.email,
    first_name: user.first_name,
    last_name: user.last_name,
    is_active: user.is_active,
    is_staff: user.is_staff,
    is_superuser: user.is_superuser,
    group_ids: user.groups.map((group) => group.id),
  };
}

export function UserManagementPanel({ areaDescription, areaTitle, moduleName }: UserManagementPanelProps) {
  const { t } = useI18n();
  const [users, setUsers] = useState<IamUser[]>([]);
  const [groups, setGroups] = useState<IamGroup[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [draft, setDraft] = useState<UserDraft>(emptyDraft);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [problem, setProblem] = useState<ApiProblem>();
  const [successKey, setSuccessKey] = useState<MessageKey>();
  const [reloadKey, setReloadKey] = useState(0);

  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedId),
    [selectedId, users],
  );
  const visibleUsers = useMemo(() => {
    const term = search.trim().toLocaleLowerCase();
    if (!term) return users;
    return users.filter((user) => [user.username, user.email, user.first_name, user.last_name]
      .some((value) => value.toLocaleLowerCase().includes(term)));
  }, [search, users]);

  function normalizeProblem(error: unknown): ApiProblem {
    return error instanceof ManagementApiError
      ? error.problem
      : { kind: "server", message: t("management.unknownError"), retryable: true };
  }

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setProblem(undefined);
    Promise.all([
      listManagementResources<IamUser>("/dealhost/api/iam/users/?ordering=username", controller.signal),
      listManagementResources<IamGroup>("/dealhost/api/iam/groups/?ordering=name", controller.signal),
    ])
      .then(([nextUsers, nextGroups]) => {
        setUsers(nextUsers);
        setGroups(nextGroups);
        setSelectedId((current) => nextUsers.some((user) => user.id === current) ? current : nextUsers[0]?.id);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setProblem(normalizeProblem(error));
      })
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  }, [reloadKey, t]);

  useEffect(() => {
    if (selectedUser) setDraft(draftFromUser(selectedUser));
    setProblem(undefined);
    setSuccessKey(undefined);
  }, [selectedUser?.id]);

  function toggleGroup(groupId: number) {
    setDraft((current) => ({
      ...current,
      group_ids: current.group_ids.includes(groupId)
        ? current.group_ids.filter((id) => id !== groupId)
        : [...current.group_ids, groupId],
    }));
  }

  async function saveUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser) return;
    setIsSaving(true);
    setProblem(undefined);
    setSuccessKey(undefined);
    try {
      const updated = await updateIamUser(selectedUser.id, draft);
      setUsers((current) => current.map((user) => user.id === updated.id ? updated : user));
      setSuccessKey("management.user.saved");
    } catch (error) {
      setProblem(normalizeProblem(error));
    } finally {
      setIsSaving(false);
    }
  }

  async function createUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setIsCreating(true);
    setProblem(undefined);
    setSuccessKey(undefined);
    try {
      const created = await createIamUser({
        username: String(form.get("username") ?? "").trim(),
        email: String(form.get("email") ?? "").trim(),
        first_name: String(form.get("first_name") ?? "").trim(),
        last_name: String(form.get("last_name") ?? "").trim(),
        password: String(form.get("password") ?? ""),
        is_active: true,
        is_staff: form.get("is_staff") === "on",
        is_superuser: false,
        group_ids: [],
      });
      setUsers((current) => [...current, created].sort((left, right) => left.username.localeCompare(right.username)));
      setSelectedId(created.id);
      formElement.reset();
      setSuccessKey("management.user.created");
    } catch (error) {
      setProblem(normalizeProblem(error));
    } finally {
      setIsCreating(false);
    }
  }

  async function changePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser) return;
    const formElement = event.currentTarget;
    const password = String(new FormData(formElement).get("password") ?? "");
    setIsChangingPassword(true);
    setProblem(undefined);
    setSuccessKey(undefined);
    try {
      await setIamUserPassword(selectedUser.id, password);
      formElement.reset();
      setSuccessKey("management.user.passwordChanged");
    } catch (error) {
      setProblem(normalizeProblem(error));
    } finally {
      setIsChangingPassword(false);
    }
  }

  async function removeUser() {
    if (!selectedUser || !window.confirm(t("management.user.deleteConfirm", { user: selectedUser.username }))) return;
    setProblem(undefined);
    setSuccessKey(undefined);
    try {
      await deleteIamUser(selectedUser.id);
      const remaining = users.filter((user) => user.id !== selectedUser.id);
      setUsers(remaining);
      setSelectedId(remaining[0]?.id);
      setSuccessKey("management.user.deleted");
    } catch (error) {
      setProblem(normalizeProblem(error));
    }
  }

  return (
    <article className="module-workspace__panel">
      <span className="section-kicker">{moduleName}</span>
      <h2>{areaTitle}</h2>
      <p>{areaDescription}</p>

      <div className="management-surface">
        <div className="management-toolbar">
          <code>/dealhost/api/iam/users/</code>
          <button onClick={() => setReloadKey((value) => value + 1)} type="button">{t("management.retry")}</button>
        </div>

        <div className="management-notice management-notice--neutral">
          <strong>{t("management.user.securityTitle")}</strong>
          <p>{t("management.user.securityDetail")}</p>
        </div>

        {isLoading ? <p className="management-state">{t("management.loading")}</p> : null}
        {problem ? (
          <div className={`management-notice management-notice--${problem.kind}`} role="alert">
            <strong>{t(`management.error.${problem.kind}` as MessageKey)}</strong>
            <p>{problem.message}</p>
            {problem.kind === "authentication" ? <a href={reconnectUrl()}>{t("management.reconnect")}</a> : null}
          </div>
        ) : null}
        {successKey ? <p className="management-success" role="status">{t(successKey)}</p> : null}

        {!isLoading ? (
          <label className="user-search">
            <span>{t("management.user.search")}</span>
            <input onChange={(event) => setSearch(event.target.value)} placeholder={t("management.user.searchPlaceholder")} type="search" value={search} />
          </label>
        ) : null}

        {visibleUsers.length > 0 ? (
          <div className="management-editor">
            <nav aria-label={t("management.user.listAria")} className="management-selector">
              {visibleUsers.map((user) => (
                <button
                  aria-current={user.id === selectedId ? "true" : undefined}
                  className={user.id === selectedId ? "management-selector__item management-selector__item--active" : "management-selector__item"}
                  key={user.id}
                  onClick={() => setSelectedId(user.id)}
                  type="button"
                >
                  <strong>{user.username}</strong>
                  <code>{user.email || t("management.user.noEmail")}</code>
                  <span>{user.oidc_identity ? t("management.user.oidc") : user.is_active ? t("management.user.active") : t("management.user.inactive")}</span>
                </button>
              ))}
            </nav>

            {selectedUser ? (
              <div className="user-editor">
                <form className="management-detail-form" onSubmit={saveUser}>
                  <div className="management-detail-form__heading">
                    <div><h3>{selectedUser.username}</h3><code>#{selectedUser.id}</code></div>
                    {selectedUser.oidc_identity ? <span className="management-revision">OIDC</span> : null}
                  </div>
                  <label><span>{t("management.user.firstName")}</span><input onChange={(event) => setDraft({ ...draft, first_name: event.target.value })} value={draft.first_name} /></label>
                  <label><span>{t("management.user.lastName")}</span><input onChange={(event) => setDraft({ ...draft, last_name: event.target.value })} value={draft.last_name} /></label>
                  <label className="management-detail-form__wide"><span>{t("management.user.email")}</span><input onChange={(event) => setDraft({ ...draft, email: event.target.value })} type="email" value={draft.email} /></label>
                  <div className="user-flags management-detail-form__wide">
                    <label className="management-checkbox"><input checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} type="checkbox" /> {t("management.user.active")}</label>
                    <label className="management-checkbox"><input checked={draft.is_staff} disabled={Boolean(selectedUser.oidc_identity)} onChange={(event) => setDraft({ ...draft, is_staff: event.target.checked })} type="checkbox" /> {t("management.user.staff")}</label>
                    <label className="management-checkbox"><input checked={draft.is_superuser} disabled={Boolean(selectedUser.oidc_identity)} onChange={(event) => setDraft({ ...draft, is_superuser: event.target.checked })} type="checkbox" /> {t("management.user.superuser")}</label>
                  </div>
                  <fieldset className="user-groups management-detail-form__wide">
                    <legend>{t("management.user.groups")}</legend>
                    {groups.map((group) => <label key={group.id}><input checked={draft.group_ids.includes(group.id)} onChange={() => toggleGroup(group.id)} type="checkbox" /> {group.name}</label>)}
                    {groups.length === 0 ? <p>{t("management.user.noGroups")}</p> : null}
                  </fieldset>
                  <div className="management-detail-form__actions">
                    <button disabled={isSaving} type="submit">{isSaving ? t("management.user.saving") : t("management.user.save")}</button>
                    <button className="management-button--danger" disabled={Boolean(selectedUser.oidc_identity)} onClick={removeUser} type="button">{t("management.user.delete")}</button>
                  </div>
                </form>

                {!selectedUser.oidc_identity ? (
                  <form className="user-password-form" onSubmit={changePassword}>
                    <h3>{t("management.user.passwordTitle")}</h3>
                    <label><span>{t("management.user.newPassword")}</span><input autoComplete="new-password" minLength={8} name="password" required type="password" /></label>
                    <button disabled={isChangingPassword} type="submit">{isChangingPassword ? t("management.user.passwordChanging") : t("management.user.passwordChange")}</button>
                  </form>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : !isLoading ? <div className="management-empty"><strong>{t("management.emptyTitle")}</strong><p>{t("management.emptyDetail")}</p></div> : null}

        <form className="management-form" onSubmit={createUser}>
          <h3>{t("management.user.createTitle")}</h3>
          <label><span>{t("management.user.username")}</span><input autoComplete="off" name="username" required /></label>
          <label><span>{t("management.user.firstName")}</span><input name="first_name" /></label>
          <label><span>{t("management.user.lastName")}</span><input name="last_name" /></label>
          <label><span>{t("management.user.email")}</span><input name="email" type="email" /></label>
          <label><span>{t("management.user.password")}</span><input autoComplete="new-password" minLength={8} name="password" required type="password" /></label>
          <label className="management-checkbox"><input name="is_staff" type="checkbox" /> {t("management.user.staff")}</label>
          <button disabled={isCreating} type="submit">{isCreating ? t("management.creating") : t("management.create")}</button>
        </form>
      </div>
    </article>
  );
}
