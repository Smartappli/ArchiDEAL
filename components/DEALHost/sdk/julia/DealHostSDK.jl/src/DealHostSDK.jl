module DealHostSDK

using HTTP
using JSON3

export DealHostClient, create_tool, create_application, list_tools, list_applications

struct DealHostClient
    base_url::String
    token::Union{Nothing,String}
    timeout_seconds::Int
end

function DealHostClient(
    base_url::AbstractString;
    token::Union{Nothing,AbstractString}=nothing,
    timeout_seconds::Integer=30,
)
    normalized_base_url = rstrip(String(base_url), '/')
    isempty(normalized_base_url) && throw(ArgumentError("base_url must be non-empty."))
    timeout_seconds > 0 || throw(ArgumentError("timeout_seconds must be positive."))

    return DealHostClient(
        normalized_base_url,
        isnothing(token) ? nothing : String(token),
        Int(timeout_seconds),
    )
end

function _request(client::DealHostClient, method::String, path::String; body=nothing, query=Dict{String,String}())
    headers = ["Accept" => "application/json"]
    if client.token !== nothing && !isempty(client.token)
        push!(headers, "Authorization" => "Bearer $(client.token)")
    end

    url = client.base_url * path
    if !isempty(query)
        filtered = filter(((k, v),) -> !isempty(v), query)
        if !isempty(filtered)
            url *= "?" * join(["$(HTTP.escapeuri(k))=$(HTTP.escapeuri(v))" for (k, v) in filtered], "&")
        end
    end

    response = if body === nothing
        HTTP.request(method, url; headers=headers, readtimeout=client.timeout_seconds)
    else
        push!(headers, "Content-Type" => "application/json")
        HTTP.request(method, url; headers=headers, body=JSON3.write(body), readtimeout=client.timeout_seconds)
    end

    if response.status >= 400
        error("dealhost request failed: status=$(response.status) body=$(String(response.body))")
    end

    return JSON3.read(String(response.body))
end

function create_tool(client::DealHostClient; name::String, slug::String, description::String="", module_ids::Vector{Int}=Int[], enabled::Bool=true)
    return _request(client, "POST", "/api/hosting/tools/";
        body=Dict("name" => name, "slug" => slug, "description" => description, "module_ids" => module_ids, "enabled" => enabled))
end

function create_application(client::DealHostClient; name::String, slug::String, description::String="", module_ids::Vector{Int}=Int[], enabled::Bool=true)
    return _request(client, "POST", "/api/hosting/applications/";
        body=Dict("name" => name, "slug" => slug, "description" => description, "module_ids" => module_ids, "enabled" => enabled))
end

function list_tools(client::DealHostClient; enabled::Union{Nothing,Bool}=nothing, module_slug::Union{Nothing,String}=nothing)
    query = Dict(
        "enabled" => (enabled === nothing ? "" : lowercase(string(enabled))),
        "module_slug" => (module_slug === nothing ? "" : module_slug),
    )
    return _request(client, "GET", "/api/hosting/tools/"; query=query)
end

function list_applications(client::DealHostClient; enabled::Union{Nothing,Bool}=nothing, module_slug::Union{Nothing,String}=nothing)
    query = Dict(
        "enabled" => (enabled === nothing ? "" : lowercase(string(enabled))),
        "module_slug" => (module_slug === nothing ? "" : module_slug),
    )
    return _request(client, "GET", "/api/hosting/applications/"; query=query)
end

end
