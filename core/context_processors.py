def grupos_usuario(request):
    if not request.user.is_authenticated:
        return {"grupos_usuario": set()}
    return {"grupos_usuario": set(request.user.groups.values_list("name", flat=True))}
