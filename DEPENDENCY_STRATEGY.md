# Estrategia de Versionado de Dependencias

## 📦 Filosofía: Siempre las Últimas Versiones

Este proyecto usa una estrategia de **"latest stable"** para todas las dependencias:

```python
# ✅ BUENO: Sin restricción de versión
pandas

# ❌ EVITAR: Versiones fijas o antiguas
pandas==2.0.0
pandas>=2.0.0
```

## 🎯 Por Qué Esta Estrategia

### Ventajas

1. **Siempre actualizado**: Obtienes bug fixes y mejoras de seguridad automáticamente
2. **Nuevas features**: Acceso inmediato a funcionalidad más reciente
3. **Simplicidad**: No preocuparte por actualizar números de versión manualmente
4. **Compatibilidad**: Menos conflictos entre dependencias modernas
5. **Aprendizaje**: Aprendes con las APIs más actuales

### Desventajas (Mitigadas)

1. **Breaking changes**: ⚠️ **Mitigado** - Las librerías modernas usan semantic versioning
2. **Reproducibilidad**: ⚠️ **No crítico** - Para desarrollo/aprendizaje, la reproducibilidad exacta no es esencial

## 📊 Versiones Actuales (Enero 2025)

| Librería | Versión Actual | Última Actualización | Notas |
|----------|----------------|---------------------|-------|
| **py-clob-client** | 0.34.4 | Ene 6, 2026 | ✅ MUY RECIENTE - Post-only orders, RFQ fixes |
| **pandas** | 2.3.3 | Sep 29, 2025 | ✅ Python 3.14 support |
| **numpy** | 2.x+ | 2025 | ✅ Major version 2.0 stable |
| **langchain** | 1.1.x | Dic 2025 | ✅ Middleware, context-aware agents |
| **langgraph** | 1.0.x | 2025 | ✅ Stable v1.0 release |
| **aiohttp** | 3.11+ | 2025 | ✅ Latest async HTTP |
| **pytest** | 8.x | 2025 | ✅ Latest testing framework |

## 🔄 Cuándo Actualizar

### Automático al Instalar
```bash
pip install -r requirements.txt
```

**Siempre instala la última versión disponible en PyPI**

### Actualización Manual
```bash
# Actualizar todo
pip install --upgrade -r requirements.txt

# Actualizar librería específica
pip install --upgrade py-clob-client
```

### Verificar Versiones Instaladas
```bash
pip list
pip show py-clob-client
pip show pandas
```

## 🛡️ Semantic Versioning

La mayoría de las librerías modernas usan **semantic versioning** (MAJOR.MINOR.PATCH):

```
1.2.3
│ │ │
│ │ └─ PATCH: Bug fixes (siempre compatible)
│ └─── MINOR: New features (backward compatible)
└───── MAJOR: Breaking changes
```

### Garantías de Compatibilidad

**LangChain 1.x**: No breaking changes hasta 2.0 ✅  
**pandas 2.x**: API estable, breaking changes solo en 3.0 ✅  
**py-clob-client 0.x**: Desarrollo activo, pero API relativamente estable ✅

## 📝 Casos Especiales

### py-clob-client (0.34.4)

**Estado**: En desarrollo activo (0.x)  
**Estabilidad**: Buena - usado en producción por Polymarket  
**Actualizaciones**: Frecuentes (varias por mes)  
**Riesgo**: Bajo - API principal estable

**Cambios recientes importantes:**
- v0.34.4 (Ene 6): Fix orderbook hash
- v0.34.3 (Ene 4): Post-only orders handling
- v0.31.0 (Dic 9): RFQ methods (Request for Quote)

### pandas (2.3.3)

**Estado**: Estable, camino a 3.0  
**Cambios**: Mostly backwards compatible  
**3.0 Preview**: Algunas features experimentales disponibles

### LangChain (1.1)

**Estado**: Stable v1.0+  
**Garantía**: No breaking changes hasta 2.0  
**Actualizaciones**: Mensual con nuevas features

## 🎓 Recomendaciones para Tu Proyecto

### Durante Desarrollo (Ahora)

✅ **USA**: Sin restricciones de versión  
✅ **ACTUALIZA**: Frecuentemente para aprender nuevas features  
✅ **MONITOREA**: Changelogs cuando algo no funciona

### Si Vas a Producción (Futuro)

Considera crear `requirements-lock.txt` con versiones exactas:

```bash
# Generar lock file con versiones exactas
pip freeze > requirements-lock.txt
```

**Cuándo usar cada uno:**

```bash
# Desarrollo: requirements.txt (latest)
pip install -r requirements.txt

# Producción: requirements-lock.txt (exact)
pip install -r requirements-lock.txt
```

## 🔍 Monitoreo de Actualizaciones

### Verificar Actualizaciones Disponibles

```bash
pip list --outdated
```

### Herramientas Útiles

```bash
# Ver dependencias del proyecto
pip-tools compile requirements.txt

# Verificar seguridad
pip-audit
```

## 🐛 Troubleshooting

### "Incompatible versions"

```bash
# Resolver conflictos
pip install --upgrade --force-reinstall -r requirements.txt
```

### "Module not found después de actualizar"

```bash
# Reinstalar desde cero
pip uninstall -r requirements.txt -y
pip install -r requirements.txt
```

### "Breaking change en nueva versión"

```bash
# Downgrade temporal a versión anterior
pip install pandas==2.2.3

# Reportar issue al proyecto
# Luego actualizar requirements.txt temporalmente
```

## 📚 Recursos

### Changelogs Importantes

- **py-clob-client**: https://github.com/Polymarket/py-clob-client/releases
- **pandas**: https://pandas.pydata.org/docs/whatsnew/index.html
- **LangChain**: https://changelog.langchain.com/
- **numpy**: https://numpy.org/news/

### Verificar Versiones en PyPI

- py-clob-client: https://pypi.org/project/py-clob-client/
- pandas: https://pypi.org/project/pandas/
- langchain: https://pypi.org/project/langchain/

## ✅ Checklist de Actualización

Cuando actualices el proyecto en el futuro:

- [ ] `pip list --outdated` para ver actualizaciones disponibles
- [ ] Revisar changelogs de librerías críticas (py-clob-client, langchain)
- [ ] `pip install --upgrade -r requirements.txt`
- [ ] Ejecutar tests: `pytest tests/`
- [ ] Ejecutar verificación: `python test_setup.py`
- [ ] Probar funcionalidad básica del bot
- [ ] Actualizar este documento si hay cambios importantes

## 🎯 Resumen

**Para tu proyecto de aprendizaje/desarrollo:**

✅ Estrategia "latest stable" es **PERFECTA**  
✅ Obtienes las features más nuevas  
✅ Aprendes con APIs modernas  
✅ Menos problemas de compatibilidad  
✅ Preparado para el futuro

**Si algún día vas a producción enterprise:**

⚠️ Considera crear `requirements-lock.txt`  
⚠️ Implementa proceso de testing antes de actualizar  
⚠️ Monitorea changelogs más de cerca

---

**Última actualización:** Enero 2025  
**Versiones verificadas:** py-clob-client 0.34.4, pandas 2.3.3, LangChain 1.1
