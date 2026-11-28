# Victorian Charts — Universal Antique Pie Chart Shader
# Pure gfx/FX visual override: zero GUI conflicts, multiplayer & achievement safe.
# Smooth antique velvet & fine paper patina (zero grid), gentle vintage toning,
# and crisp 1px dark radial seams for every Pie Chart (>= 36px) in the game.

Includes = {
	"cw/pdxgui.fxh"
	"cw/pdxgui_sprite.fxh"
}

VertexShader =
{
	MainCode VertexShader
	{
		Input = "VS_INPUT_PDX_GUI"
		Output = "VS_OUTPUT_PDX_GUI"
		Code
		[[
			PDX_MAIN
			{
				VS_OUTPUT_PDX_GUI Out;

				float2 Normalised = ( Input.Position.xy + 1.0f ) / 2.0f;
				float2 PixelPos = Normalised * Input.LeftTop_WidthHeight.zw + Input.LeftTop_WidthHeight.xy;

				Out.Position = PixelToScreenSpace( PixelPos );
				Out.UV0      = Normalised;
				Out.Color    = Input.Color;

				return Out;
			}
		]]
	}

	MainCode VertexShaderPieChart
	{
		Input = "VS_INPUT_PDX_GUI"
		Output = "VS_OUTPUT_PDX_GUI"
		Code
		[[
			PDX_MAIN
			{
				return PdxGuiDefaultVertexShader( Input );
			}
		]]
	}
}


PixelShader =
{
	TextureSampler Texture
	{
		Ref = PdxTexture0
		MagFilter = "Linear"
		MinFilter = "Linear"
		MipFilter = "Linear"
		SampleModeU = "Clamp"
		SampleModeV = "Clamp"
	}

	TextureSampler MaskTexture
	{
		Ref = PdxTexture1
		MagFilter = "Linear"
		MinFilter = "Linear"
		MipFilter = "Linear"
		SampleModeU = "Clamp"
		SampleModeV = "Clamp"
	}

	MainCode PixelShader
	{
		ConstantBuffer( PdxConstantBuffer2 )
		{
			float3 HighlightColor;
		};

		Input = "VS_OUTPUT_PDX_GUI"
		Output = "PDX_COLOR"
		Code
		[[
			PDX_MAIN
			{
				float4 Mask  = PdxTex2DLod0( MaskTexture, Input.UV0 );
				float4 Color = SampleImageSprite( Texture, Input.UV0 );

				float4 OutColor = Color * Input.Color * Mask;
				#ifndef NO_HIGHLIGHT
					OutColor.rgb += HighlightColor;
				#endif
				return OutColor;
			}
		]]
	}

	MainCode PixelShaderPieChart
	{
		ConstantBuffer( PdxConstantBuffer2 )
		{
			float2 WidgetScreenSize;
			float StartAngle;
			int NumSlices;
		};

		ConstantBuffer( PdxConstantBuffer3 )
		{
			# See CPdxGuiGfxTypePieChart::Render, each slice uses 2 float4
			# first float4 contains: x = StartAngle, y = EndAngle, z = highlight
			# second float4 contains the color
			float4 PieSliceData[2048];
		};

		Input = "VS_OUTPUT_PDX_GUI"
		Output = "PDX_COLOR"
		Code
		[[
			int FindSlice( float Angle, int StartIndex )
			{
				for ( int i = StartIndex; i < NumSlices; ++i )
				{
					int SliceDataIndex = 2 * i;
					if ( Angle > PieSliceData[SliceDataIndex].x && Angle <= PieSliceData[SliceDataIndex].y )
					{
						return i;
					}
				}

				return 0;
			}

			float VicHash( float2 p )
			{
				float3 p3 = frac( float3( p.x, p.y, p.x ) * 0.1031 );
				p3 += dot( p3, float3( p3.y, p3.z, p3.x ) + 33.33 );
				return frac( ( p3.x + p3.y ) * p3.z );
			}

			float VicValueNoise( float2 p )
			{
				float2 i = floor( p );
				float2 f = frac( p );
				float2 u = f * f * ( 3.0 - 2.0 * f );
				float a = VicHash( i );
				float b = VicHash( i + float2( 1.0, 0.0 ) );
				float c = VicHash( i + float2( 0.0, 1.0 ) );
				float d = VicHash( i + float2( 1.0, 1.0 ) );
				return lerp( lerp( a, b, u.x ), lerp( c, d, u.x ), u.y );
			}

			float3 VicOverlayChannel( float3 Base, float BlendVal )
			{
				float3 Low  = 2.0 * Base * BlendVal;
				float3 High = 1.0 - 2.0 * ( 1.0 - Base ) * ( 1.0 - BlendVal );
				float3 Mask = float3(
					Base.r < 0.5 ? 0.0 : 1.0,
					Base.g < 0.5 ? 0.0 : 1.0,
					Base.b < 0.5 ? 0.0 : 1.0
				);
				return lerp( Low, High, Mask );
			}

			float3 ApplyVictorianMaterial( float3 BaseRgb, float2 LocalPx )
			{
				// 1. Subtle antique tone deepening (~8%, rich without feeling dim)
				float3 Rgb = BaseRgb * 0.92 + float3( 0.020, 0.018, 0.016 ) * 0.08;

				// 2. Silky multi-octave organic velvet & parchment patina (zero periodic grid)
				float CloudLow  = VicValueNoise( LocalPx * 0.032 );
				float CloudMid  = VicValueNoise( LocalPx * 0.085 + float2( 17.3, 9.1 ) );
				float PaperSoft = VicValueNoise( LocalPx * 0.22 + float2( 31.7, 53.2 ) );
				float Patina    = CloudLow * 0.52 + CloudMid * 0.33 + PaperSoft * 0.15;

				// Neutral-mean Overlay gives smooth depth variation without darkening
				float OverlayVal = saturate( 0.50 + ( Patina - 0.5 ) * 0.28 );
				Rgb = lerp( Rgb, VicOverlayChannel( Rgb, OverlayVal ), 0.18 );

				// 3. Gentle warm velvet haze (~7%) calming loud neon colors into vintage pigments
				float VelvetVal = lerp( 0.46, 0.56, CloudLow * 0.65 + CloudMid * 0.35 );
				float3 VelvetRgb = float3( VelvetVal * 1.01, VelvetVal * 0.99, VelvetVal * 0.95 );
				Rgb = lerp( Rgb, VelvetRgb, 0.075 );

				return Rgb;
			}

			PDX_MAIN
			{
				float4 Mask  = PdxTex2DLod0( MaskTexture, Input.UV0 );
				float4 Color = SampleImageSprite( Texture, Input.UV0 );

				float2 Direction = Input.UV0 - vec2( 0.5 );
				float DirLen = length( Direction );
				float2 DirectionNormalized = ( DirLen > 0.00001 ) ? ( Direction / DirLen ) : float2( 1.0, 0.0 );

				float TwoPi = 2.0 * PI;
				float Angle = acos( clamp( DirectionNormalized.x, -1.0, 1.0 ) );
				Angle = ( DirectionNormalized.y < 0.0 ) ? Angle : TwoPi - Angle;
				Angle -= StartAngle;

				float DistanceFromCenter = max( length( Direction * WidgetScreenSize ), 0.001 );

				float ArcLength = 0.5;
				float SearchAngle = min( 0.5, ArcLength / DistanceFromCenter );

				float StartSearchAngle = Angle - SearchAngle;
				if ( StartSearchAngle < 0.0 )
				{
					StartSearchAngle += TwoPi;
				}
				int StartSlice = FindSlice( StartSearchAngle, 0 );

				float EndSearchAngle = StartSearchAngle + SearchAngle * 2.0;
				int EndSlice = 0;
				if ( EndSearchAngle > TwoPi )
				{
					EndSearchAngle -= TwoPi;
					EndSlice = FindSlice( EndSearchAngle, 0 );
				}
				else
				{
					EndSlice = FindSlice( EndSearchAngle, StartSlice );
				}

				#ifndef NO_HIGHLIGHT
					float Highlight = 0.0;
				#endif
				float4 SliceColor = vec4( 0.0 );
				if ( StartSlice != EndSlice )
				{
					float FullSearchAngleInv = 0.5 / SearchAngle;
					int CurrentSlice = StartSlice;
					float CurrentAngle = StartSearchAngle;
					for ( int i = 0; i < NumSlices; ++i )
					{
						int SliceDataIndex = 2 * CurrentSlice;
						float EndAngle = ( EndSearchAngle < PieSliceData[SliceDataIndex].x ) ? PieSliceData[SliceDataIndex].y : min( PieSliceData[SliceDataIndex].y, EndSearchAngle );
						float SliceFraction = ( EndAngle - CurrentAngle ) * FullSearchAngleInv;
						#ifndef NO_HIGHLIGHT
							Highlight += PieSliceData[SliceDataIndex].z * SliceFraction;
						#endif
						SliceColor += PieSliceData[SliceDataIndex + 1] * SliceFraction;

						if ( CurrentSlice == EndSlice )
						{
							break;
						}

						CurrentSlice++;
						CurrentAngle = EndAngle;
						if ( CurrentSlice == NumSlices )
						{
							CurrentSlice = 0;
							CurrentAngle = 0.0;
						}
					}
				}
				else
				{
					int SliceDataIndex = StartSlice * 2;
					#ifndef NO_HIGHLIGHT
						Highlight = PieSliceData[SliceDataIndex].z;
					#endif
					SliceColor = PieSliceData[SliceDataIndex + 1];
				}

				float4 OutColor = SliceColor * Color * Input.Color * Mask;

				float MinSize = min( WidgetScreenSize.x, WidgetScreenSize.y );
				if ( MinSize >= 36.0 )
				{
					float2 LocalPx = Input.UV0 * WidgetScreenSize;
					OutColor.rgb = ApplyVictorianMaterial( OutColor.rgb, LocalPx );

					float RadiusPx = MinSize * 0.5;
					float3 SeamColor = float3( 0.07, 0.052, 0.044 );

					// Crisp 1px dark radial seams matching treemap border weight
					if ( NumSlices > 1 )
					{
						float CenterAngle = Angle - TwoPi * floor( Angle / TwoPi );
						int CenterSlice = FindSlice( CenterAngle, 0 );
						float SliceStart = PieSliceData[2 * CenterSlice].x;
						float SliceEnd   = PieSliceData[2 * CenterSlice].y;
						float SliceSpan  = SliceEnd - SliceStart;

						if ( SliceSpan < TwoPi - 0.005 )
						{
							float DistStart = abs( CenterAngle - SliceStart );
							DistStart = min( DistStart, TwoPi - DistStart );
							float DistEnd = abs( SliceEnd - CenterAngle );
							DistEnd = min( DistEnd, TwoPi - DistEnd );

							float SeamPx = min( DistStart, DistEnd ) * DistanceFromCenter;
							float SeamMask = 1.0 - smoothstep( 0.40, 1.15, SeamPx );
							float HubFade = smoothstep( 3.0, 8.0, DistanceFromCenter );
							float SliverFade = smoothstep( 2.0, 5.5, SliceSpan * DistanceFromCenter );

							OutColor.rgb = lerp( OutColor.rgb, SeamColor, SeamMask * HubFade * SliverFade * 0.66 );
						}

						// Subtle center junction point
						float CenterPin = ( 1.0 - smoothstep( 1.2, 3.0, DistanceFromCenter ) ) * 0.28;
						OutColor.rgb = lerp( OutColor.rgb, SeamColor, CenterPin );
					}

					// Crisp 1px dark outer rim matching treemap cell perimeter
					float OuterSeam = smoothstep( RadiusPx - 2.0, RadiusPx - 0.7, DistanceFromCenter ) * 0.60;
					OutColor.rgb = lerp( OutColor.rgb, SeamColor, OuterSeam );
				}

				#ifndef NO_HIGHLIGHT
					OutColor.rgb += vec3( Highlight );
				#endif
				return OutColor;
			}
		]]
	}
}


BlendState BlendState
{
	BlendEnable = yes
	SourceBlend = "SRC_ALPHA"
	DestBlend = "INV_SRC_ALPHA"
}

DepthStencilState DepthStencilState
{
	DepthEnable = no
}


Effect Default
{
	VertexShader = "VertexShader"
	PixelShader = "PixelShader"
}

Effect NoHighlightDefault
{
	VertexShader = "VertexShader"
	PixelShader = "PixelShader"
	Defines = {"NO_HIGHLIGHT"}
}

Effect PieChartDefault
{
	VertexShader = "VertexShaderPieChart"
	PixelShader = "PixelShaderPieChart"
}

Effect PieChartNoHighlightDefault
{
	VertexShader = "VertexShaderPieChart"
	PixelShader = "PixelShaderPieChart"
	Defines = {"NO_HIGHLIGHT"}
}
